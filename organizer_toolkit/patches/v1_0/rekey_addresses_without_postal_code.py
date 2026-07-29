"""Recompute address keys without the postal code, merging doors it had split.

The dedupe key used to include the postal code. That looked harmless but broke the key
in exactly the case it exists for: a canvasser at a door rarely knows the ZIP, so the
same address entered with and without one produced two records and split that door's
history. It had already happened to 6069 Reinhard St, and only 3 of 244 addresses
carried a postal code at all.

Keys are recomputed from `build_address_key`, which no longer considers postal code.
Where that collapses two records into one, the older is kept, anything the newer knew
(coordinates, district, parcel ID, postal code) is copied onto it, references are
repointed, and the duplicate is deleted.

Idempotent: a second run finds no collisions and rewrites each key to the value it
already holds.
"""

import frappe

from organizer_toolkit.address_utils import build_address_key

# Copied onto the surviving record when it has no value of its own.
BACKFILL_FIELDS = (
	"postal_code",
	"state",
	"location",
	"latitude",
	"longitude",
	"municipal_district",
	"municipal_parcel_id",
)

# Doctypes holding a Link to OT Address that must follow the merge.
REFERENCING = (("OT Constituent", "address"), ("OT Canvass Attempt", "address"))


def execute():
	if not frappe.db.table_exists("OT Address"):
		return

	rows = frappe.get_all(
		"OT Address",
		fields=["name", "address_line_1", "address_line_2", "city", *BACKFILL_FIELDS],
		order_by="creation asc",
	)

	groups = {}
	for row in rows:
		key = build_address_key(row.address_line_1, row.address_line_2, row.city)
		if key:
			groups.setdefault(key, []).append(row)

	merged = 0
	for group in groups.values():
		keeper = group[0]
		for duplicate in group[1:]:
			_merge(keeper, duplicate)
			merged += 1

	# Blank every key to a unique placeholder first. Assigning a final key that another
	# row still holds would trip the unique index part-way through the pass.
	frappe.db.sql("UPDATE `tabOT Address` SET address_key = CONCAT('__rekey__', `name`)")

	for key, group in groups.items():
		frappe.db.set_value("OT Address", group[0].name, "address_key", key, update_modified=False)

	frappe.db.commit()

	print(f"  rekeyed {len(groups)} address(es) without postal code")
	if merged:
		print(f"  merged {merged} duplicate door(s) that the postal code had split apart")


def _merge(keeper, duplicate):
	for doctype, fieldname in REFERENCING:
		if not frappe.db.table_exists(doctype):
			continue

		for name in frappe.get_all(doctype, filters={fieldname: duplicate.name}, pluck="name"):
			frappe.db.set_value(doctype, name, fieldname, keeper.name, update_modified=False)

	for field in BACKFILL_FIELDS:
		if not keeper.get(field) and duplicate.get(field):
			frappe.db.set_value("OT Address", keeper.name, field, duplicate.get(field), update_modified=False)
			keeper[field] = duplicate.get(field)

	# force: the duplicate's own key still collides until the rekey pass runs.
	frappe.delete_doc("OT Address", duplicate.name, ignore_permissions=True, force=True)

	print(f"    merged {duplicate.name} into {keeper.name} ({keeper.address_line_1})")
