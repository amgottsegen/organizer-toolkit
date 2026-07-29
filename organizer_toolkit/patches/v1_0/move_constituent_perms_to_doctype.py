"""Drop the Custom DocPerm rows shadowing OT Constituent's doctype permissions.

Frappe's `Meta.set_custom_permissions` replaces a doctype's entire permission list as
soon as a single Custom DocPerm row exists for it. OT Constituent had six such rows --
almost certainly created by someone opening Role Permissions Manager, which snapshots
the JSON into Custom DocPerm on first edit -- so the `permissions` array in
ot_constituent.json was inert. Adding a role there appeared to work and granted nothing.

The identical matrix now lives in the doctype JSON, so deleting these rows is a no-op
for effective access; it just restores source as the source of truth.

Re-running is harmless: once the rows are gone there is nothing to delete.
"""

import frappe
from frappe.permissions import reset_perms

DOCTYPE = "OT Constituent"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	existing = frappe.db.count("Custom DocPerm", {"parent": DOCTYPE})

	if not existing:
		print(f"  {DOCTYPE}: no Custom DocPerm rows; already using doctype JSON.")
		return

	reset_perms(DOCTYPE)
	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()

	print(f"  {DOCTYPE}: removed {existing} Custom DocPerm row(s); permissions now come from the doctype JSON.")
