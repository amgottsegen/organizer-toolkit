# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import json
import os

import frappe
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import today
from shapely.geometry import Point, shape

from organizer_toolkit.utils import get_coordinates


class OTConstituent(Document):
	def validate(self):
		if self.mobile_phone == "+1-":
			self.mobile_phone = None

		if self.home_phone == "+1-":
			self.home_phone = None

	def before_save(self):
		# We set this here since virtual fields do not work with
		#   View Settings -> Title Field as of 2025-08-26
		self.full_name = (
			f"{self.first_name}"
			+ ((' "' + self.preferred_name + '"') if self.preferred_name else "")
			+ ((" " + self.last_name) if self.last_name else "")
		)

	def autoname(self):
		date_str = today().replace("-", "")
		month_str = date_str[:6]
		counter = getseries(f"CNST-{month_str}-", 5)
		number = counter.split("-")[-1]
		self.name = f"CNST-{date_str}-{number}"


@frappe.whitelist()
def geocode_address(doc_name):
	doc = frappe.get_doc("OT Constituent", doc_name)

	##Error handling for missing address components
	if doc.street_address is None or doc.city is None or doc.street_address == "" or doc.city == "":
		frappe.throw(
			f"Error in doc {doc.name}: Please ensure the constituent has both a street address and city before geocoding."
		)
		return

	address_string = ", ".join(filter(None, [doc.street_address, doc.city, doc.state]))

	r = get_coordinates(address_string)

	if r is None:
		frappe.throw("Geocoding failed. Please check the address and try again.")
		frappe.errprint(f"Geocoding failed for constituent {doc.name} with address: {address_string}")
		return

	lat = r["latitude"]
	lon = r["longitude"]

	doc.location = frappe.as_json(
		{
			"type": "FeatureCollection",
			"features": [
				{
					"type": "Feature",
					"geometry": {"type": "Point", "coordinates": [lon, lat]},
					"properties": {},
				}
			],
		}
	)

	doc.council_district = _find_council_district(lat, lon)

	doc.save()
	return {"lat": lat, "lon": lon}


def _load_council_districts():
	geojson_path = frappe.get_app_path(
		"organizer_toolkit", "public", "geojson", "Council_Districts_2024.geojson"
	)
	with open(geojson_path) as f:
		return json.load(f)


def _find_council_district(lat, lon):
	districts = _load_council_districts()
	point = Point(lon, lat)  # Shapely uses (lon, lat) order

	for feature in districts["features"]:
		polygon = shape(feature["geometry"])
		if polygon.contains(point):
			return feature["properties"]["DISTRICT"]

	return None
