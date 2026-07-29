"""Seed OT Locality Settings from the packaged preset, once.

Deliberately a patch rather than a fixture. Fixtures re-import on every `bench migrate`,
which would silently revert whatever the organization configured in the UI -- fine for
reference data like OT Language, wrong for a settings document.

Values come from `locality.DEFAULTS` so the preset has exactly one home: change that
dict (or just edit the settings page) to run the toolkit in another city.

Idempotent twice over: it exits if the doc has already been configured, and only fills
fields that are still empty.
"""

import frappe

from organizer_toolkit.locality import DEFAULTS, SETTINGS_DOCTYPE


def execute():
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return

	settings = frappe.get_single(SETTINGS_DOCTYPE)

	filled = []
	for fieldname, value in DEFAULTS.items():
		if not settings.get(fieldname):
			settings.set(fieldname, value)
			filled.append(fieldname)

	if not filled:
		# Values are already set, but the Property Setters they drive may not exist --
		# they are what carry the configured labels and defaults into Quick Entry and
		# list views. Re-materialize them rather than assuming.
		settings.apply_meta_overrides()
		frappe.db.commit()
		print("  OT Locality Settings already configured; refreshed field overrides.")
		return

	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()

	print(f"  seeded OT Locality Settings ({settings.locality_name}): {', '.join(filled)}")
