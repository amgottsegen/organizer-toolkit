"""Single point of access for everything that varies from one city to another.

Organizer Toolkit was built for Philadelphia, but nothing outside this module should
know that. Place-specific values live in the `OT Locality Settings` single doctype;
the constants below are only fallbacks so a fresh install works before anyone opens
the settings page.

To run the toolkit in a different city: open OT Locality Settings, change the values,
and upload that city's district boundaries as GeoJSON. No code change required.

The one thing here that is genuinely US-shaped is address normalization in
`address_utils` -- street types, directionals and 5-digit ZIPs. That would need real
work for a non-US deployment and is deliberately out of scope.
"""

import json
import os
from functools import lru_cache
from urllib.parse import quote

import frappe

SETTINGS_DOCTYPE = "OT Locality Settings"

# Philadelphia, used when the settings doc has no value for a field.
DEFAULTS = {
	"locality_name": "Philadelphia, PA",
	"default_city": "Philadelphia",
	"default_state": "PA",
	"map_center_latitude": 39.9526,
	"map_center_longitude": -75.1652,
	"map_default_zoom": 12,
	"district_label": "Council District",
	"district_property_key": "DISTRICT",
	"parcel_id_label": "OPA Account Number",
	"parcel_lookup_url": "https://atlas.phila.gov/{address}/property",
}

# Shipped with the app so a default install has working district lookup with nothing
# uploaded. An attachment on the settings doc takes precedence over this.
BUNDLED_DISTRICT_GEOJSON = ("public", "geojson", "Council_Districts_2024.geojson")


def get_locality(fieldname=None):
	"""Return one setting, or the whole mapping, falling back to DEFAULTS.

	Reads through Frappe's document cache, so this is cheap to call per request.
	"""
	try:
		# For a Single, name == doctype; passing both is the reliably cacheable form.
		settings = frappe.get_cached_doc(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
	except Exception:
		# The doctype may not exist yet during install or an early patch.
		settings = None

	def resolve(key):
		value = settings.get(key) if settings else None
		# Single doctypes store unset values as empty strings, and an unset Float comes
		# back as 0 -- neither is a meaningful coordinate or zoom level.
		return DEFAULTS[key] if value in (None, "", 0) else value

	if fieldname:
		return resolve(fieldname)

	return {key: resolve(key) for key in DEFAULTS}


def get_district_boundaries_path():
	"""Filesystem path to the district GeoJSON, uploaded or bundled."""
	attached = None

	try:
		attached = frappe.get_cached_value(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, "district_boundaries")
	except Exception:
		pass

	if attached:
		# Attach fields store a URL (/files/x or /private/files/x), not a path.
		relative = attached.lstrip("/")
		if relative.startswith("private/"):
			path = frappe.get_site_path(relative)
		else:
			path = frappe.get_site_path("public", relative)

		if os.path.exists(path):
			return path

		frappe.log_error(
			title="Locality: district boundaries missing",
			message=f"{SETTINGS_DOCTYPE} points at {attached}, which is not on disk. "
			"Falling back to the bundled boundaries.",
		)

	return frappe.get_app_path("organizer_toolkit", *BUNDLED_DISTRICT_GEOJSON)


@lru_cache(maxsize=2)
def _district_polygons(path, property_key):
	"""Parse and prepare district polygons once per process.

	Cached because bulk geocoding hits this once per address, and the boundary file is
	static -- re-reading and rebuilding the polygons every time is pure waste. Keyed on
	path and property key so changing either produces a fresh entry.
	"""
	from shapely.geometry import shape

	with open(path) as f:
		districts = json.load(f)

	return tuple(
		(shape(feature["geometry"]), feature.get("properties", {}).get(property_key))
		for feature in districts.get("features", [])
	)


def find_district(lat, lon):
	"""Return the municipal district containing this point, or None."""
	from shapely.geometry import Point

	polygons = _district_polygons(get_district_boundaries_path(), get_locality("district_property_key"))
	point = Point(lon, lat)  # Shapely uses (lon, lat) order

	for polygon, district in polygons:
		if district is not None and polygon.contains(point):
			return district

	return None


def get_parcel_lookup_url(address):
	"""Build the external property-record link, or None if none is configured."""
	template = get_locality("parcel_lookup_url")

	if not template:
		return None

	return template.replace("{address}", quote(str(address or "")))


def clear_locality_cache():
	_district_polygons.cache_clear()
	frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
