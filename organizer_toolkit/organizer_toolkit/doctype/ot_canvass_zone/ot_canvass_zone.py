# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import json

import frappe
from frappe import _
from frappe.model.document import Document

# Feature geometries that can enclose addresses. A zone drawn as a marker or a line
# encloses nothing, so it is ignored rather than treated as an empty zone.
AREA_GEOMETRIES = ("Polygon", "MultiPolygon")


class OTCanvassZone(Document):
	def boundary_polygons(self):
		"""Shapely polygons for this zone's drawn boundary.

		The Geolocation field stores a FeatureCollection, and Frappe's map widget lets an
		organizer draw more than one shape -- so a zone can legitimately be several
		disjoint areas.
		"""
		from shapely.geometry import shape

		if not self.location:
			return []

		try:
			data = json.loads(self.location) if isinstance(self.location, str) else self.location
		except (ValueError, TypeError):
			frappe.log_error(
				title="Canvass zone: unreadable boundary",
				message=f"{self.name} has a boundary that is not valid JSON.",
			)
			return []

		return [
			shape(feature["geometry"])
			for feature in (data.get("features") or [])
			if (feature.get("geometry") or {}).get("type") in AREA_GEOMETRIES
		]


@frappe.whitelist()
def addresses_within(zone):
	"""Names of geocoded addresses falling inside a zone's boundary.

	Only addresses with real coordinates are considered. An ungeocoded address stores
	0/0, which sits in the Gulf of Guinea and so is inside nobody's zone -- but relying
	on that accident would be fragile, so it is excluded explicitly.
	"""
	from shapely.geometry import Point

	zone_doc = frappe.get_cached_doc("OT Canvass Zone", zone)
	polygons = zone_doc.boundary_polygons()

	if not polygons:
		frappe.throw(
			_("{0} has no boundary drawn yet, so there is nothing to pull addresses from.").format(
				zone_doc.name
			)
		)

	candidates = frappe.get_all(
		"OT Address",
		filters={"location": ["is", "set"]},
		fields=["name", "latitude", "longitude"],
		limit_page_length=0,
	)

	inside = []
	for address in candidates:
		if not address.latitude and not address.longitude:
			continue

		point = Point(address.longitude, address.latitude)  # shapely wants (lon, lat)

		if any(polygon.contains(point) for polygon in polygons):
			inside.append(address.name)

	return inside
