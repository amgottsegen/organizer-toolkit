# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from organizer_toolkit.map_layers import DEFAULT_MAX_FEATURES, detect_csv_columns, get_mappable_doctypes


class OTMapLayer(Document):
	def validate(self):
		self.validate_source()
		self.fill_in_csv_columns()
		self.clamp_style()

	def validate_source(self):
		if self.source_type == "File":
			self.clear_doctype_fields()
			return

		self.clear_file_fields()

		if self.source_doctype not in get_mappable_doctypes():
			frappe.throw(
				_(
					"{0} has no map coordinates. A layer needs a doctype with a Geolocation field "
					"named location, or a latitude and longitude pair."
				).format(frappe.bold(self.source_doctype))
			)

		if self.label_field and not frappe.get_meta(self.source_doctype).has_field(self.label_field):
			frappe.throw(_("{0} has no field called {1}.").format(self.source_doctype, self.label_field))

	def clear_doctype_fields(self):
		"""A leftover doctype filter on a file layer would silently do nothing."""
		self.source_doctype = None
		self.label_field = None
		self.filters_json = "[]"

	def clear_file_fields(self):
		self.source_file = None
		self.latitude_column = None
		self.longitude_column = None
		self.label_column = None

	def fill_in_csv_columns(self):
		"""Guess the CSV's coordinate columns so the common case needs no configuration.

		Only fills blanks -- a column set by hand is a correction of this guess and must
		survive the next save.
		"""
		if self.source_type != "File" or not self.source_file:
			return

		for fieldname, detected in detect_csv_columns(self).items():
			if not self.get(fieldname) and detected:
				self.set(fieldname, detected)

	def clamp_style(self):
		"""Keep the styling inside what Leaflet will actually draw."""
		self.marker_size = max(cint(self.marker_size) or 6, 1)
		self.line_weight = max(cint(self.line_weight), 0)
		self.max_features = max(cint(self.max_features) or DEFAULT_MAX_FEATURES, 1)

		opacity = flt(self.fill_opacity)
		self.fill_opacity = min(max(opacity, 0), 1) if opacity else 0.6
