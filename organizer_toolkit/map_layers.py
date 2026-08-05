# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
"""Reference layers that can be shown on any map in the desk.

Generalises what `doorknocking/doorknocking_map.py` hardcodes in folium -- Lots, Houses,
Members, Zones, Districts as toggleable layers -- into something an organizer can
configure. The point is cutting turf: you cannot draw a sensible zone boundary over an
empty basemap, you draw it around pins you already have.
"""
import json
import os

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

# Guesses for CSV headers, tried in order. `target_lots.csv` uses lat/lng.
LATITUDE_ALIASES = ("latitude", "lat", "y")
LONGITUDE_ALIASES = ("longitude", "lng", "lon", "long", "x")
LABEL_ALIASES = ("label", "address", "location", "address_line_1", "name", "title")

# GeoJSON properties worth showing in a popup when a file does not say which to use.
GEOJSON_LABEL_KEYS = ("Name", "name", "label", "title", "NAME")

CACHE_PREFIX = "ot_map_layer_file"
CACHE_TTL = 24 * 60 * 60

DEFAULT_MAX_FEATURES = 2000


@frappe.whitelist()
def get_layers():
	"""Style metadata for every enabled layer -- deliberately no feature data.

	Opening a map costs exactly one small request: this list is what builds the layer
	control, and a layer nobody ticks on is never fetched at all.
	"""
	return frappe.get_list(
		"OT Map Layer",
		filters={"enabled": 1},
		fields=[
			"name",
			"layer_name",
			"description",
			"show_by_default",
			"display_order",
			"source_type",
			"source_doctype",
			"color",
			"marker_shape",
			"marker_size",
			"fill_opacity",
			"line_weight",
		],
		# The shared default stack. A viewer's own reordering is layered on top of this
		# client-side, so rearranging a map does not change what anyone else sees.
		order_by="display_order asc, layer_name asc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_layer_features(layer):
	"""The GeoJSON for one layer, capped at its `max_features`."""
	doc = frappe.get_cached_doc("OT Map Layer", layer)
	doc.check_permission("read")

	if not doc.enabled:
		return {"type": "FeatureCollection", "features": [], "total": 0, "truncated": False}

	features = _doctype_features(doc) if doc.source_type == "DocType" else _file_features(doc)
	cap = cint(doc.max_features) or DEFAULT_MAX_FEATURES

	return {
		"type": "FeatureCollection",
		"features": features[:cap],
		"total": len(features),
		"truncated": len(features) > cap,
	}


# -- saved maps --------------------------------------------------------------------


@frappe.whitelist()
def get_saved_maps():
	"""Every saved view, for the picker on the map. Names only -- no layer data."""
	return frappe.get_list(
		"OT Saved Map",
		filters={"enabled": 1},
		fields=["name", "map_name", "description"],
		order_by="map_name asc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_saved_map(saved_map):
	"""The full recipe: where to look, and which layers in which order."""
	doc = frappe.get_cached_doc("OT Saved Map", saved_map)
	doc.check_permission("read")

	return {
		"name": doc.name,
		"map_name": doc.map_name,
		"center_latitude": doc.center_latitude,
		"center_longitude": doc.center_longitude,
		"zoom": doc.zoom,
		# Row order is the stacking order, first on top.
		"layers": [row.layer for row in doc.layers if row.layer],
	}


@frappe.whitelist()
def save_current_view(
	map_name, layers=None, center_latitude=None, center_longitude=None, zoom=None
):
	"""Create or update a saved map from what someone is currently looking at.

	Upserts on the name. Saving onto an existing map runs the normal permission check, so
	a volunteer cannot overwrite an organizer's view by guessing its name -- they get the
	usual write error instead.
	"""
	layers = frappe.parse_json(layers) or []

	if frappe.db.exists("OT Saved Map", map_name):
		doc = frappe.get_doc("OT Saved Map", map_name)
		doc.layers = []
	else:
		doc = frappe.new_doc("OT Saved Map")
		doc.map_name = map_name

	doc.center_latitude = center_latitude
	doc.center_longitude = center_longitude
	doc.zoom = zoom

	for layer in layers:
		doc.append("layers", {"layer": layer})

	doc.save()

	return {"name": doc.name, "layers": len(doc.layers)}


@frappe.whitelist()
def get_mappable_doctypes():
	"""Doctypes a map can plot: a Geolocation field named `location`, or a lat/lon pair.

	The names are not negotiable -- `frappe.geo.utils.get_coords` looks for exactly these,
	and so does the native map view (`map_view.js:72`).
	"""
	geolocation = _doctypes_with_field("location", fieldtype="Geolocation")
	pairs = _doctypes_with_field("latitude") & _doctypes_with_field("longitude")

	candidates = geolocation | pairs
	if not candidates:
		return []

	# DocField rows also belong to child tables, which have no list or map view.
	return frappe.get_all(
		"DocType",
		filters={"name": ["in", list(candidates)], "istable": 0},
		pluck="name",
		order_by="name asc",
		limit_page_length=0,
	)


def _doctypes_with_field(fieldname, fieldtype=None):
	filters = {"fieldname": fieldname}
	if fieldtype:
		filters["fieldtype"] = fieldtype

	standard = frappe.get_all("DocField", filters=filters, pluck="parent", limit_page_length=0)
	custom = frappe.get_all("Custom Field", filters=filters, pluck="dt", limit_page_length=0)

	return set(standard) | set(custom)


# -- DocType-backed layers ---------------------------------------------------------


def _doctype_features(doc):
	from frappe.geo.utils import get_coords

	if not doc.source_doctype:
		return []

	filters = frappe.parse_json(doc.filters_json) or []

	if _has_cross_table_filter(doc.source_doctype, filters):
		names = _names_matching(doc.source_doctype, filters)
		if not names:
			return []
		filters = [[doc.source_doctype, "name", "in", names]]

	# get_coords speaks two dialects -- a Geolocation field named `location`, or a
	# latitude/longitude pair -- and enforces read permission on the source doctype on
	# the way through (geo/utils.py get_coords_conditions). Reimplementing it would mean
	# reimplementing that check too.
	kind = "location_field" if frappe.get_meta(doc.source_doctype).has_field("location") else "coordinates"
	collection = get_coords(doc.source_doctype, filters, kind)

	features = [f for f in (collection.get("features") or []) if _has_real_coordinates(f)]
	_add_labels(doc, features)

	return features


def _has_cross_table_filter(doctype, filters):
	"""Does any filter reach outside the source doctype's own table?

	A filter's first element is normally the source doctype itself. When it is not -- a
	child table, like the activities on `volunteers_for` -- the condition names a table
	`get_coords` never joins, since it builds a bare `SELECT ... FROM tabDocType WHERE`.
	The condition compiles happily and then MariaDB rejects it as an unknown column.
	"""
	if not isinstance(filters, (list, tuple)):
		# A dict of filters cannot express a table other than its own.
		return False

	return any(
		isinstance(f, (list, tuple)) and len(f) >= 4 and f[0] and f[0] != doctype for f in filters
	)


def _names_matching(doctype, filters):
	"""Resolve a cross-table filter to a list of names.

	frappe.get_list goes through DatabaseQuery, which does know how to join child tables,
	so the full filter language works here. The result is handed back to get_coords as a
	plain `name in (...)`, which keeps the permission check and the geometry handling in
	one place rather than growing a second implementation of both.
	"""
	return frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=0)


def _has_real_coordinates(feature):
	"""Drop Null Island.

	`create_gps_markers` (geo/utils.py:48) applies no filtering, so a row that was never
	geocoded -- 0/0, because Frappe Float columns are NOT NULL -- plots off the coast of
	Africa and drags `fitBounds` out into the Atlantic with it.
	"""
	geometry = feature.get("geometry") or {}

	if not geometry.get("type"):
		return False

	if geometry["type"] != "Point":
		return True

	coordinates = geometry.get("coordinates") or []

	return len(coordinates) >= 2 and not (flt(coordinates[0]) == 0 and flt(coordinates[1]) == 0)


def _add_labels(doc, features):
	"""Give every pin something readable in its popup.

	`get_coords` only returns `name`, which for an autonamed doctype is a hash. One extra
	query is cheaper than teaching the shared helper about title fields.
	"""
	field = doc.label_field or frappe.get_meta(doc.source_doctype).get_title_field()
	names = [(f.get("properties") or {}).get("name") for f in features]
	names = [name for name in names if name]

	labels = {}
	if field and field != "name" and names:
		labels = {
			row.name: row.get(field)
			for row in frappe.get_all(
				doc.source_doctype,
				filters={"name": ["in", names]},
				fields=["name", field],
				limit_page_length=0,
			)
		}

	for feature in features:
		properties = feature.setdefault("properties", {})
		properties["label"] = labels.get(properties.get("name")) or properties.get("name")


# -- File-backed layers ------------------------------------------------------------


def _file_features(doc):
	path = resolve_file_path(doc.source_file)

	# Keyed on the file's mtime and the column mapping, so replacing the file or fixing a
	# wrong column guess invalidates the entry on its own. `target_stewards.csv` is 1.5 MB.
	cache_key = ":".join(
		[
			CACHE_PREFIX,
			doc.name,
			cstr(os.path.getmtime(path)),
			cstr(doc.latitude_column),
			cstr(doc.longitude_column),
			cstr(doc.label_column),
		]
	)

	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	with open(path, "rb") as handle:
		content = handle.read()

	features = (
		_parse_geojson(content)
		if path.lower().endswith((".geojson", ".json"))
		else _parse_csv(content, doc)
	)

	frappe.cache().set_value(cache_key, features, expires_in_sec=CACHE_TTL)

	return features


def resolve_file_path(file_url):
	"""Filesystem path for an attached file.

	Goes through the File doctype when a record exists, and resolves the URL by hand when
	one does not -- the bundled data files (`target_lots.csv`, `zones_v2.geojson`) were
	dropped into `private/files` directly and have no File record. `basename` is what
	keeps a hand-typed `/private/files/../../..` from escaping the site.
	"""
	if not file_url:
		frappe.throw(_("This layer has no file attached."))

	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if name:
		return frappe.get_doc("File", name).get_full_path()

	if file_url.startswith("/private/files/"):
		path = frappe.get_site_path("private", "files", os.path.basename(file_url))
	elif file_url.startswith("/files/"):
		path = frappe.get_site_path("public", "files", os.path.basename(file_url))
	else:
		frappe.throw(_("{0} is not a file in this site.").format(file_url))

	if not os.path.exists(path):
		frappe.throw(_("{0} is missing from the site's files.").format(file_url))

	return path


def _parse_geojson(content):
	try:
		data = json.loads(content)
	except ValueError:
		frappe.throw(_("This file is not valid GeoJSON."))

	if data.get("type") == "FeatureCollection":
		features = data.get("features") or []
	elif data.get("type") == "Feature":
		features = [data]
	else:
		frappe.throw(_("GeoJSON must be a Feature or a FeatureCollection."))

	for feature in features:
		properties = feature.setdefault("properties", {})
		if not properties.get("label"):
			properties["label"] = next(
				(properties[key] for key in GEOJSON_LABEL_KEYS if properties.get(key)), ""
			)

	return features


def _parse_csv(content, doc):
	from frappe.utils.csvutils import read_csv_content

	rows = read_csv_content(content)
	if not rows:
		return []

	header = [cstr(column).strip() for column in rows[0]]
	latitude = column_index(header, doc.latitude_column, LATITUDE_ALIASES)
	longitude = column_index(header, doc.longitude_column, LONGITUDE_ALIASES)

	if latitude is None or longitude is None:
		frappe.throw(
			_("Could not find latitude and longitude columns in {0}. Set them on the layer.").format(
				doc.source_file
			)
		)

	label = column_index(header, doc.label_column, LABEL_ALIASES)
	features = []

	for row in rows[1:]:
		if len(row) <= max(latitude, longitude):
			continue

		lat, lon = flt(row[latitude]), flt(row[longitude])
		if not lat and not lon:
			continue

		features.append(
			{
				"type": "Feature",
				"properties": {
					"label": cstr(row[label]) if label is not None and len(row) > label else ""
				},
				# GeoJSON wants them the other way round.
				"geometry": {"type": "Point", "coordinates": [lon, lat]},
			}
		)

	return features


def column_index(header, configured, aliases):
	"""Position of a column, by explicit name if given and by convention if not."""
	lowered = [column.lower() for column in header]

	if configured:
		configured = configured.strip().lower()
		return lowered.index(configured) if configured in lowered else None

	for alias in aliases:
		if alias in lowered:
			return lowered.index(alias)

	return None


def detect_csv_columns(doc):
	"""Header names for the latitude, longitude and label columns of an attached CSV.

	Returns whatever it can work out; the caller decides what to do about the gaps.
	"""
	from frappe.utils.csvutils import read_csv_content

	path = resolve_file_path(doc.source_file)

	if path.lower().endswith((".geojson", ".json")):
		return {}

	with open(path, "rb") as handle:
		# The header is all that is needed, so do not read a 1.5 MB file to find it.
		first_line = handle.readline()

	rows = read_csv_content(first_line)
	if not rows:
		return {}

	header = [cstr(column).strip() for column in rows[0]]

	def name_at(index):
		return header[index] if index is not None else None

	return {
		"latitude_column": name_at(column_index(header, doc.latitude_column, LATITUDE_ALIASES)),
		"longitude_column": name_at(column_index(header, doc.longitude_column, LONGITUDE_ALIASES)),
		"label_column": name_at(column_index(header, doc.label_column, LABEL_ALIASES)),
	}
