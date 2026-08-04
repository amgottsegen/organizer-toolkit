"""Make each constituent's coordinates match its address.

`OT Constituent.location` fetches from `address.location`, but `fetch_from` only copies
at save time, so every constituent that already existed when the field was added needs
filling in once. From here on the fetch handles new records and
`OT Address.propagate_location` handles late geocodes.

Authoritative rather than fill-the-blanks, because the blanks are not the only problem.
Constituents were geocoded directly before that moved to OT Address, and Frappe never
drops the column for a removed field -- so adding a field named `location` back to this
doctype resurfaces those pre-migration values. They are close but not equal to the
address's own coordinates, and some sit on constituents that have no address at all.
Overwriting from the address is what makes the field mean what it says.

Written straight to the column rather than through the ORM: this copies a value that is
already authoritative elsewhere, and saving every constituent would fire the full
validation and hook stack for no gain.
"""

import frappe


def execute():
	if not frappe.db.table_exists("OT Constituent") or not frappe.db.table_exists("OT Address"):
		return

	if not frappe.get_meta("OT Constituent").has_field("location"):
		return

	constituents = frappe.get_all(
		"OT Constituent", fields=["name", "address", "location"], limit_page_length=0
	)

	if not constituents:
		return

	addresses = {c.address for c in constituents if c.address}
	locations = (
		{
			row.name: row.location
			for row in frappe.get_all(
				"OT Address",
				filters={"name": ["in", list(addresses)]},
				fields=["name", "location"],
				limit_page_length=0,
			)
		}
		if addresses
		else {}
	)

	located = cleared = 0

	for constituent in constituents:
		wanted = locations.get(constituent.address) or None

		if (constituent.location or None) == wanted:
			continue

		frappe.db.set_value(
			"OT Constituent", constituent.name, "location", wanted, update_modified=False
		)

		if wanted:
			located += 1
		else:
			# Either the address is not geocoded yet, or this was a stale pin left behind
			# by the pre-migration column. Both cases: better blank than wrong.
			cleared += 1

	frappe.db.commit()

	print(f"  located {located} constituent(s); cleared {cleared} without a geocoded address")
