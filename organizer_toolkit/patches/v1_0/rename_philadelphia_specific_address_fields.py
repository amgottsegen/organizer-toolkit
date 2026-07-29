"""Generalize Philadelphia-specific field names on OT Address.

    opa_account_number -> municipal_parcel_id   (OPA = Philadelphia's assessor)
    council_district   -> municipal_district

Runs post_model_sync, so the doctype already carries the new fieldnames and the old
columns are still present as orphans -- `rename_field` copies the values across with
`UPDATE tabOT Address SET new = old`.

Idempotent: once the old column is gone from the schema there is nothing to copy, and
re-running is a no-op.
"""

import frappe
from frappe.model.utils.rename_field import rename_field

RENAMES = (
	("opa_account_number", "municipal_parcel_id"),
	("council_district", "municipal_district"),
)


def execute():
	if not frappe.db.table_exists("OT Address"):
		return

	frappe.reload_doctype("OT Address")

	for old, new in RENAMES:
		if not frappe.db.has_column("OT Address", old):
			continue

		if not frappe.db.has_column("OT Address", new):
			# The doctype sync should have created it; bail loudly rather than silently
			# leaving the data stranded in the old column.
			frappe.log_error(
				title="Locality rename skipped",
				message=f"OT Address.{new} does not exist; cannot migrate from {old}.",
			)
			continue

		rename_field("OT Address", old, new)
		print(f"  renamed OT Address.{old} -> {new}")

	frappe.db.commit()
