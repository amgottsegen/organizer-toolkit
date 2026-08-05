# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt

# Leaflet's own limits. Outside them setView silently clamps, which looks like the saved
# map not working rather than the zoom being wrong.
MIN_ZOOM = 1
MAX_ZOOM = 20


class OTSavedMap(Document):
	def validate(self):
		self.drop_duplicate_layers()
		self.clamp_view()

	def drop_duplicate_layers(self):
		"""One row per layer.

		A layer listed twice would have two positions in the stack, and whichever was
		applied last would win -- so the order shown in the table would not be the order
		drawn on the map.
		"""
		seen = set()
		unique_rows = []

		for row in self.layers:
			if not row.layer or row.layer in seen:
				continue

			seen.add(row.layer)
			unique_rows.append(row)

		if len(unique_rows) != len(self.layers):
			self.layers = unique_rows
			for index, row in enumerate(self.layers, start=1):
				row.idx = index

	def clamp_view(self):
		if self.zoom:
			self.zoom = min(max(cint(self.zoom), MIN_ZOOM), MAX_ZOOM)

		# A half-set centre would send the map to the equator. Treat it as unset, which
		# means "open wherever the map would have opened anyway".
		if not (flt(self.center_latitude) and flt(self.center_longitude)):
			self.center_latitude = None
			self.center_longitude = None
