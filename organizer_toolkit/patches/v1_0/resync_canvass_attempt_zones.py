"""Re-source every doorknock's zone from its walk list instead of its address.

`OT Canvass Attempt.zone` originally fetched from `address.zone`, which is current
geography. That is the wrong anchor for a record of work: boundaries get redrawn, and a
redraw would reach back and relabel doors knocked months earlier as belonging to turf
that did not exist at the time.

The walk list is what the door was actually canvassed for, so that is where the label
comes from now. A doorknock with no walk list has no zone -- there is nothing to record.
"""

import frappe


def execute():
	for doctype in ("OT Canvass Attempt", "OT Walk List"):
		if not frappe.db.table_exists(doctype):
			return

	labelled = 0

	for walk_list in frappe.get_all("OT Walk List", fields=["name", "zone"], limit_page_length=0):
		attempts = frappe.get_all(
			"OT Canvass Attempt",
			filters={"walk_list": walk_list.name},
			pluck="name",
			limit_page_length=0,
		)

		for attempt in attempts:
			frappe.db.set_value(
				"OT Canvass Attempt", attempt, "zone", walk_list.zone, update_modified=False
			)

		if walk_list.zone:
			labelled += len(attempts)

	# Anything geometry stamped that has no walk list behind it is not a record of
	# anything, so it goes.
	orphans = frappe.get_all(
		"OT Canvass Attempt",
		filters={"walk_list": ["is", "not set"], "zone": ["is", "set"]},
		pluck="name",
		limit_page_length=0,
	)

	for attempt in orphans:
		frappe.db.set_value("OT Canvass Attempt", attempt, "zone", None, update_modified=False)

	frappe.db.commit()

	print(
		f"  labelled {labelled} doorknock(s) from their walk list; "
		f"cleared {len(orphans)} with no walk list"
	)
