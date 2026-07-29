"""Extract OT Constituent's inline address fields into OT Address records.

Runs post_model_sync, which means `address` (the new Link) already exists and the seven
old columns are still present -- Frappe never drops columns for removed fields, it just
orphans them. That is what lets this read the legacy data with raw SQL after the fields
are gone from the doctype.

Idempotent: constituents already carrying a link are skipped, and addresses are matched
on the normalized `address_key`, so a re-run reports zero remaining work.

Before running against production, take a backup, restore it to a staging site and run:

    bench --site <staging> execute \\
        organizer_toolkit.patches.v1_0.migrate_constituent_addresses.dry_run
"""

import frappe

from organizer_toolkit.address_utils import build_address_key

# The inline fields being retired. `street_address` is the one that matters -- without a
# street there is nothing to deduplicate on and the row cannot be migrated.
LEGACY_COLUMNS = (
	"street_address",
	"address_line_2",
	"city",
	"state",
	"postal_code",
	"council_district",
	"location",
)


def execute():
	_migrate(dry_run=False)
	_drop_stale_property_setters()


def _drop_stale_property_setters():
	"""Remove list-view tweaks that pointed at the inline address fields.

	Frappe ignores Property Setters for fields that no longer exist, so this is tidiness
	rather than a fix -- but a setter naming a deleted field is a trap for whoever reads
	the customization list next.
	"""
	stale = frappe.get_all(
		"Property Setter",
		filters={"doc_type": "OT Constituent", "field_name": ["in", LEGACY_COLUMNS]},
		pluck="name",
	)

	for name in stale:
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)

	if stale:
		print(f"  removed {len(stale)} stale property setter(s) for retired address fields")


def dry_run():
	"""Report what `execute` would do, without writing anything."""
	_migrate(dry_run=True)


def _fetch_legacy_rows():
	"""Read the orphaned columns directly -- they are no longer in the DocType meta."""
	if not frappe.db.has_column("OT Constituent", "street_address"):
		return None

	available = [c for c in LEGACY_COLUMNS if frappe.db.has_column("OT Constituent", c)]

	# `address` is absent if the dry run is invoked on a staging site before the doctype
	# sync has added it. Select it only when present so the report still works.
	if frappe.db.has_column("OT Constituent", "address"):
		available = ["address", *available]

	columns = ", ".join(f"`{c}`" for c in available)

	return frappe.db.sql(f"SELECT `name`, {columns} FROM `tabOT Constituent`", as_dict=True)


def _migrate(dry_run):
	rows = _fetch_legacy_rows()

	if rows is None:
		print("No legacy address columns found -- nothing to migrate.")
		return

	stats = {
		"scanned": len(rows),
		"already_linked": 0,
		"no_street": 0,
		"blank_city": 0,
		"addresses_created": 0,
		"addresses_reused": 0,
		"constituents_linked": 0,
		"with_geocode": 0,
	}
	# Group first, create second. Several constituents can share one door, and only one
	# of them may be the geocoded row -- creating from whichever happened to come first
	# would silently discard the others' coordinates.
	groups = {}

	for row in rows:
		if row.get("address"):
			stats["already_linked"] += 1
			continue

		key = build_address_key(
			row.get("street_address"), row.get("address_line_2"), row.get("city")
		)

		if not key:
			stats["no_street"] += 1
			continue

		if not (row.get("city") or "").strip():
			stats["blank_city"] += 1

		groups.setdefault(key, []).append(row)

	for key, group in groups.items():
		existing = frappe.db.get_value("OT Address", {"address_key": key}, "name")

		if existing:
			address_name = existing
			stats["addresses_reused"] += 1
		else:
			merged = _merge_group(group)
			stats["addresses_created"] += 1
			if merged.get("location"):
				stats["with_geocode"] += 1
			address_name = None if dry_run else _create_address(merged)

		for row in group:
			stats["constituents_linked"] += 1

			if not dry_run:
				frappe.db.set_value(
					"OT Constituent", row["name"], "address", address_name, update_modified=False
				)

	_report(stats, {k: [r["name"] for r in v] for k, v in groups.items()}, dry_run)

	if not dry_run:
		frappe.db.commit()


def _merge_group(group):
	"""Combine constituents at one door into a single address payload.

	City is part of the dedupe key, so every row in a group already agrees on it. The
	remaining fields can vary, and there the first non-empty value across the group wins.
	"""
	base = dict(group[0])

	for field in ("state", "postal_code", "council_district", "location"):
		if not base.get(field):
			base[field] = next((r.get(field) for r in group if r.get(field)), None)

	return base


def _create_address(row):
	doc = frappe.get_doc(
		{
			"doctype": "OT Address",
			"address_line_1": row.get("street_address"),
			"address_line_2": row.get("address_line_2"),
			"city": row.get("city"),
			"state": row.get("state"),
			"postal_code": row.get("postal_code"),
			# Source column on OT Constituent keeps its old Philadelphia-specific name;
			# the target field on OT Address is the generalized one.
			"municipal_district": row.get("council_district"),
			"location": row.get("location"),
			"source": "Data Import",
		}
	)
	# Let validate/before_save compute address_key and the flat lat/lon columns, so the
	# migration produces exactly what normal data entry would.
	doc.insert(ignore_permissions=True)

	return doc.name


def _report(stats, collapsing, dry_run):
	mode = "DRY RUN -- no changes written" if dry_run else "MIGRATION COMPLETE"
	print(f"\n{mode}")
	print(f"  constituents scanned      {stats['scanned']}")
	print(f"  already linked (skipped)  {stats['already_linked']}")
	print(f"  OT Address to create      {stats['addresses_created']}")
	print(f"  OT Address reused         {stats['addresses_reused']}")
	print(f"  constituents to link      {stats['constituents_linked']}")
	print(f"  carrying geocode data     {stats['with_geocode']}")

	if stats["no_street"]:
		print(f"\n  WARNING {stats['no_street']} constituent(s) have no street address and were skipped.")

	if stats["blank_city"]:
		print(f"  WARNING {stats['blank_city']} constituent(s) have a street but no city.")

	shared = {k: v for k, v in collapsing.items() if len(v) > 1}
	if shared:
		print(f"\n  {len(shared)} address(es) are shared by multiple constituents (expected for households):")
		for key, names in sorted(shared.items(), key=lambda kv: -len(kv[1]))[:10]:
			print(f"    {len(names):>3} x  {key.split('|')[0]}  ({', '.join(names[:3])}{'...' if len(names) > 3 else ''})")
		if len(shared) > 10:
			print(f"    ... and {len(shared) - 10} more")

	print()
