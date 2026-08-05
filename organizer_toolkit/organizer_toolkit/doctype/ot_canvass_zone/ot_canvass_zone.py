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
	def on_update(self):
		"""A zone is a shape, so redrawing it silently changes which doors are in it.

		Nothing else would notice -- the addresses already carry a stamped zone -- so the
		boundary has to go back and correct them. Backgrounded because a real deployment
		has tens of thousands of addresses and this is point-in-polygon over all of them.
		"""
		if not (self.has_value_changed("location") or self.has_value_changed("is_active")):
			return

		frappe.enqueue(
			"organizer_toolkit.organizer_toolkit.doctype.ot_canvass_zone.ot_canvass_zone.restamp_addresses",
			queue="long",
			# One pass covers every zone, so several edits in a row need only one job.
			job_id="ot_restamp_canvass_zones",
			deduplicate=True,
			enqueue_after_commit=True,
		)

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


def active_zone_polygons():
	"""(name, polygons) for every active zone, in a stable order.

	Zones are free to overlap, so an address can fall in more than one. Ordering by name
	means the one it gets stamped with is at least reproducible rather than dependent on
	the order rows came back in.
	"""
	zones = []

	for name in frappe.get_all(
		"OT Canvass Zone",
		filters={"is_active": 1},
		pluck="name",
		order_by="name asc",
		limit_page_length=0,
	):
		polygons = frappe.get_cached_doc("OT Canvass Zone", name).boundary_polygons()

		if polygons:
			zones.append((name, polygons))

	return zones


def find_zone(latitude, longitude, zones=None):
	"""The active zone containing this point, or None.

	Pass `zones` when looping over many addresses -- otherwise every call re-reads and
	re-parses every boundary.
	"""
	from shapely.geometry import Point

	# 0/0 is the ungeocoded sentinel, and it is in nobody's zone.
	if not latitude and not longitude:
		return None

	point = Point(longitude, latitude)  # shapely wants (lon, lat)

	for name, polygons in active_zone_polygons() if zones is None else zones:
		if any(polygon.contains(point) for polygon in polygons):
			return name

	return None


def restamp_addresses():
	"""Re-derive which zone each geocoded address currently sits in.

	Addresses only. A doorknock's zone comes from the walk list it was worked from, so
	that it stays the zone the door was canvassed for -- redrawing a boundary must not
	reach back and relabel work that already happened.

	Writes straight to the column: this is a derived value, and saving every address
	would fire geocoding hooks and duplicate checks for a field none of them look at.
	Callers commit -- background jobs and patches each do that themselves.
	"""
	zones = active_zone_polygons()
	changed = 0

	for address in frappe.get_all(
		"OT Address",
		filters={"location": ["is", "set"]},
		fields=["name", "latitude", "longitude", "zone"],
		limit_page_length=0,
	):
		zone = find_zone(address.latitude, address.longitude, zones)

		if (address.zone or None) == zone:
			continue

		frappe.db.set_value("OT Address", address.name, "zone", zone, update_modified=False)
		changed += 1

	return changed


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
