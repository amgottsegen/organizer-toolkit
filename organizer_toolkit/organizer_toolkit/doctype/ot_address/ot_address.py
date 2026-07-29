# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from organizer_toolkit.address_utils import (
	build_address_key,
	build_location_geojson,
	extract_lat_lon,
)
from organizer_toolkit.locality import find_district
from organizer_toolkit.utils import get_coordinates


class OTAddress(Document):
	def validate(self):
		self.address_key = build_address_key(
			self.address_line_1, self.address_line_2, self.city, self.postal_code
		)

		if not self.address_key:
			frappe.throw(_("Street Address is required."))

		self.check_for_duplicate()

	def before_save(self):
		# Keep the flat columns in step with the Geolocation field so the map can filter
		# by bounding box without parsing GeoJSON for every row.
		#
		# Frappe Float columns are NOT NULL, so an ungeocoded address stores 0/0 rather
		# than NULL. Callers must exclude that sentinel -- 0,0 is a real coordinate in
		# the Gulf of Guinea and would otherwise plot as a legitimate pin.
		coords = extract_lat_lon(self.location)

		self.latitude, self.longitude = coords if coords else (0, 0)

	def check_for_duplicate(self):
		"""Surface the unique constraint on address_key as a usable message.

		Without this the canvasser gets a raw MariaDB duplicate-key error and no way to
		reach the record they should have been editing.
		"""
		filters = {"address_key": self.address_key}
		if not self.is_new():
			filters["name"] = ("!=", self.name)

		existing = frappe.db.get_value("OT Address", filters, "name")

		if existing:
			frappe.throw(
				_("This address already exists as {0}.").format(
					f'<a href="/app/ot-address/{existing}">{existing}</a>'
				),
				title=_("Duplicate Address"),
			)


def find_or_create_address(
	address_line_1, address_line_2=None, city=None, state=None, postal_code=None, source="Manual Entry"
):
	"""Return the OT Address for these components, creating it only if new.

	Deduplication happens on the normalized address_key, so callers can pass whatever
	the user typed. Used by the migration patches and by field data entry.
	"""
	address_key = build_address_key(address_line_1, address_line_2, city, postal_code)

	if not address_key:
		return None

	existing = frappe.db.get_value("OT Address", {"address_key": address_key}, "name")
	if existing:
		return frappe.get_doc("OT Address", existing)

	doc = frappe.get_doc(
		{
			"doctype": "OT Address",
			"address_line_1": address_line_1,
			"address_line_2": address_line_2,
			"city": city,
			"state": state,
			"postal_code": postal_code,
			"source": source,
		}
	)
	doc.insert()

	return doc


@frappe.whitelist()
def geocode_address(doc_name):
	doc = frappe.get_doc("OT Address", doc_name)

	if not doc.address_line_1 or not doc.city:
		frappe.throw(
			_("Address {0} needs both a street address and a city before geocoding.").format(doc.name)
		)

	address_string = ", ".join(filter(None, [doc.address_line_1, doc.city, doc.state]))

	r = get_coordinates(address_string)

	if r is None:
		frappe.log_error(
			title="Geocoding failed",
			message=f"Geocoding failed for address {doc.name}: {address_string}",
		)
		frappe.throw(_("Geocoding failed. Please check the address and try again."))

	lat = r["latitude"]
	lon = r["longitude"]

	doc.location = build_location_geojson(lat, lon)
	doc.municipal_district = find_district(lat, lon)
	doc.save()

	return {"lat": lat, "lon": lon}
