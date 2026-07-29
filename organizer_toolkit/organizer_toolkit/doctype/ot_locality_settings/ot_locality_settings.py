# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import (
	delete_property_setter,
	make_property_setter,
)
from frappe.model.document import Document

from organizer_toolkit.locality import clear_locality_cache

# Settings that have to reach Frappe's *metadata* rather than just runtime code.
# Quick Entry builds its dialog straight from the doctype meta and never runs a form
# script, so a field default set only in JS would not appear on the fastest data-entry
# path -- the one canvassers actually use. Materializing Property Setters keeps this
# doctype the single source of truth while still reaching Quick Entry, list filters and
# reports.
#   (target doctype, target fieldname, meta property) -> field on this settings doc
META_OVERRIDES = {
	("OT Address", "city", "default"): "default_city",
	("OT Address", "state", "default"): "default_state",
	("OT Address", "municipal_parcel_id", "label"): "parcel_id_label",
	("OT Address", "municipal_district", "label"): "district_label",
	# OT Event Space keeps its own inline address fields rather than linking to
	# OT Address, but its defaults should still follow the configured city.
	("OT Event Space", "city", "default"): "default_city",
	("OT Event Space", "state", "default"): "default_state",
}


class OTLocalitySettings(Document):
	def validate(self):
		if self.map_default_zoom and not (1 <= self.map_default_zoom <= 20):
			frappe.throw(_("Map Default Zoom must be between 1 and 20."))

	def on_update(self):
		# District polygons and the boot payload are cached per process; drop them so a
		# settings change takes effect without a bench restart.
		clear_locality_cache()
		self.apply_meta_overrides()

	def apply_meta_overrides(self):
		touched = set()

		for (doctype, fieldname, prop), settings_field in META_OVERRIDES.items():
			if not frappe.db.exists("DocType", doctype):
				continue

			touched.add(doctype)

			value = (self.get(settings_field) or "").strip()

			if value:
				make_property_setter(
					doctype,
					fieldname,
					prop,
					value,
					"Data",
					validate_fields_for_doctype=False,
				)
			else:
				# Blank means "no override" -- fall back to whatever the doctype JSON
				# declares rather than stamping an empty label onto the form.
				delete_property_setter(doctype, prop, fieldname)

		for doctype in touched:
			frappe.clear_cache(doctype=doctype)
