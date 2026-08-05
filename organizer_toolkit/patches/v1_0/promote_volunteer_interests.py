"""Turn the constituent's `volunteers_for` rows into OT Volunteer Interest records.

Same problem as the RSVPs: a child table on OT Constituent means recording "I'll help
knock doors" requires write access to the whole person. Promoting the RSVPs alone would
not have let OT Constituent drop off write, because this table would still have needed it.

Unlike the RSVPs this is a copy, not a reparent, because `OT Activity Child` is also used
on OT Canvass Attempt -- where it is the right shape, since a volunteer already owns the
doorknock they are recording. So the child doctype stays, and only the constituent-side
rows become records.
"""

import frappe


def execute():
	for doctype in ("OT Activity Child", "OT Volunteer Interest", "OT Constituent"):
		if not frappe.db.table_exists(doctype):
			return

	rows = frappe.db.sql(
		"""SELECT parent AS constituent, activity, creation FROM `tabOT Activity Child`
		   WHERE parenttype = 'OT Constituent' AND ifnull(activity, '') != ''""",
		as_dict=True,
	)

	created = skipped = 0

	for row in rows:
		if not frappe.db.exists("OT Constituent", row.constituent):
			continue

		if frappe.db.exists(
			"OT Volunteer Interest", {"constituent": row.constituent, "activity": row.activity}
		):
			skipped += 1
			continue

		frappe.get_doc(
			{
				"doctype": "OT Volunteer Interest",
				"constituent": row.constituent,
				"activity": row.activity,
				"recorded_on": row.creation.date() if row.creation else None,
				# Where these came from was never recorded, so do not invent it.
				"source": "Other",
			}
		).insert(ignore_permissions=True)
		created += 1

	frappe.db.commit()

	print(f"  created {created} volunteer interest(s); {skipped} already recorded")
