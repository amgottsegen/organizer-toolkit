"""Turn OT Event RSVP child rows into standalone records.

A child table has no permissions of its own -- it inherits its parent's. So recording
"yes, I'll be there" at a door required write access to the constituent's entire record:
name, phone, assessment, everything. That is why OT Volunteer could edit every
constituent in the system, and it is what this patch exists to end.

Promotion is in place rather than a copy: the rows already live in `tabOT Event RSVP`,
carrying the constituent in `parent`. Moving that value into a real link field and
clearing the child-table bookkeeping is the whole migration, so no name changes and
nothing pointing at an RSVP has to be rewritten.

Duplicates are merged on the way through. Nothing enforced one-RSVP-per-event while this
was a child table, and the data drifted.
"""

import frappe

# Values that mean "nobody filled this in", so a duplicate carrying only these can be
# folded into its sibling without losing anything.
BLANK = (None, "", "-", 0, "Not Contacted")

MERGEABLE_FIELDS = (
	"rsvp",
	"rsvp_notes",
	"last_contact_result",
	"needs_transportation",
	"transportation_notes",
	"needs_childcare",
	"childcare_notes",
	"attended",
	"origin",
)


def execute():
	if not frappe.db.table_exists("OT Event RSVP"):
		return

	if not frappe.get_meta("OT Event RSVP").has_field("constituent"):
		return

	merged = merge_duplicates()
	promoted = promote()

	frappe.db.commit()

	print(f"  promoted {promoted} RSVP(s) to standalone records; merged {merged} duplicate(s)")


def merge_duplicates():
	"""Collapse rows that share a constituent and an event, keeping the fullest one."""
	groups = frappe.db.sql(
		"""SELECT parent, event FROM `tabOT Event RSVP`
		   WHERE ifnull(parent, '') != '' AND ifnull(event, '') != ''
		   GROUP BY parent, event HAVING count(*) > 1""",
		as_dict=True,
	)

	merged = 0

	for group in groups:
		rows = frappe.db.sql(
			"""SELECT * FROM `tabOT Event RSVP` WHERE parent = %s AND event = %s
			   ORDER BY creation ASC""",
			(group.parent, group.event),
			as_dict=True,
		)

		# The row with the most answered fields survives; ties go to the oldest, which is
		# the one other records are most likely to have been created alongside.
		keeper = max(rows, key=lambda row: sum(1 for f in MERGEABLE_FIELDS if row.get(f) not in BLANK))
		updates = {}

		for row in rows:
			if row.name == keeper.name:
				continue

			for field in MERGEABLE_FIELDS:
				if keeper.get(field) in BLANK and row.get(field) not in BLANK:
					updates[field] = row.get(field)
					keeper[field] = row.get(field)

			frappe.db.delete("OT Event RSVP", {"name": row.name})
			merged += 1

		if updates:
			frappe.db.set_value("OT Event RSVP", keeper.name, updates, update_modified=False)

	return merged


def promote():
	"""Move `parent` into the constituent link and drop the child-table bookkeeping."""
	rows = frappe.db.sql(
		"""SELECT name, parent FROM `tabOT Event RSVP`
		   WHERE ifnull(parent, '') != '' AND ifnull(constituent, '') = ''""",
		as_dict=True,
	)

	for row in rows:
		frappe.db.set_value(
			"OT Event RSVP",
			row.name,
			{"constituent": row.parent, "parent": "", "parenttype": "", "parentfield": ""},
			update_modified=False,
		)

	# constituent_name fetches from the link, which only fires on save -- fill it here so
	# the list view is readable without touching 1000 records through the ORM.
	frappe.db.sql(
		"""UPDATE `tabOT Event RSVP` rsvp
		   JOIN `tabOT Constituent` c ON c.name = rsvp.constituent
		   SET rsvp.constituent_name = c.full_name
		   WHERE ifnull(rsvp.constituent_name, '') = ''"""
	)

	return len(rows)
