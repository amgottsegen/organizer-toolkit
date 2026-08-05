# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from organizer_toolkit.map_layers import get_layer_features, get_mappable_doctypes

CSV_CONTENT = """location,owner_1,lat,lng
1725 N 26TH ST,PHILADELPHIA LAND BANK,39.981772,-75.176942
1729 N 26TH ST,PHILADELPHIA LAND BANK,39.981853,-75.176924
"""

# Same shape as zones_v2.geojson: the label lives in a "Name" property.
GEOJSON_CONTENT = """{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"Name": "Zone 9: Sunday"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [-75.15, 39.98], [-75.14, 39.98], [-75.14, 39.99], [-75.15, 39.98]
            ]]}
        }
    ]
}"""


class TestOTMapLayer(FrappeTestCase):
	def setUp(self):
		self.files = []

	def tearDown(self):
		for path in self.files:
			if os.path.exists(path):
				os.remove(path)

		frappe.set_user("Administrator")
		frappe.db.rollback()

	# -- helpers ------------------------------------------------------------------

	def _site_file(self, filename, content):
		path = frappe.get_site_path("private", "files", filename)

		with open(path, "w") as handle:
			handle.write(content)

		self.files.append(path)

		return f"/private/files/{filename}"

	def _layer(self, **kwargs):
		defaults = {
			"doctype": "OT Map Layer",
			"layer_name": "Test Layer",
			"source_type": "DocType",
			"source_doctype": "OT Address",
		}
		defaults.update(kwargs)

		return frappe.get_doc(defaults).insert()

	def _address(self, street, city="Philadelphia"):
		from organizer_toolkit.address_utils import build_location_geojson

		# Creating an address otherwise queues a Nominatim lookup.
		with patch("frappe.enqueue"):
			return frappe.get_doc(
				{
					"doctype": "OT Address",
					"address_line_1": street,
					"city": city,
					"location": build_location_geojson(39.99, -75.14),
				}
			).insert()

	# -- doctype-backed layers ----------------------------------------------------

	def test_doctype_layer_honours_its_filters(self):
		"""The whole point of cutting turf around a subset: the filter has to bite."""
		wanted = self._address("101 Filtered In St", city="Philadelphia")
		self._address("202 Filtered Out St", city="Camden")

		layer = self._layer(
			filters_json='[["OT Address","city","=","Philadelphia"]]',
			label_field="address_line_1",
		)

		labels = [f["properties"]["label"] for f in get_layer_features(layer.name)["features"]]

		self.assertIn(wanted.address_line_1, labels)
		self.assertNotIn("202 Filtered Out St", labels)

	def test_labels_come_from_the_label_field(self):
		"""get_coords only returns `name`, which for an autonamed doctype is a hash."""
		address = self._address("303 Labelled St")
		layer = self._layer(label_field="address_line_1")

		feature = next(
			f
			for f in get_layer_features(layer.name)["features"]
			if f["properties"]["name"] == address.name
		)

		self.assertEqual(feature["properties"]["label"], "303 Labelled St")

	def test_doctype_layer_delegates_to_the_permission_checked_helper(self):
		"""frappe.geo.utils.get_coords enforces read permission on the source doctype on
		the way through. Querying the table directly would skip that."""
		layer = self._layer(filters_json='[["OT Address","city","=","Philadelphia"]]')

		with patch(
			"frappe.geo.utils.get_coords", return_value={"features": []}
		) as get_coords:
			get_layer_features(layer.name)

		get_coords.assert_called_once_with(
			"OT Address", [["OT Address", "city", "=", "Philadelphia"]], "location_field"
		)

	def test_null_island_is_dropped(self):
		"""create_gps_markers does no filtering, so an ungeocoded row -- 0/0, because
		Frappe Float columns are NOT NULL -- would plot off the coast of Africa and drag
		fitBounds out into the Atlantic with it."""
		layer = self._layer()

		collection = {
			"features": [
				{"properties": {"name": "real"}, "geometry": {"type": "Point", "coordinates": [-75.1, 39.9]}},
				{"properties": {"name": "never geocoded"}, "geometry": {"type": "Point", "coordinates": [0, 0]}},
			]
		}

		with patch("frappe.geo.utils.get_coords", return_value=collection):
			names = [f["properties"]["name"] for f in get_layer_features(layer.name)["features"]]

		self.assertEqual(names, ["real"])

	# -- filters that reach into a child table ------------------------------------

	def test_a_child_table_filter_selects_the_right_people(self):
		"""A filter naming another table -- here the languages child table -- compiles to
		a condition get_coords cannot run: it builds a bare SELECT ... FROM tabDocType
		with no joins, so MariaDB rejects the column as unknown. The names are resolved
		first instead, through get_list, which does know how to join."""
		language = self._language()
		speaker = self._constituent("Willing Volunteer", languages=[language])
		self._constituent("Uninvolved Person")

		layer = self._layer(
			layer_name="Test Volunteers",
			source_doctype="OT Constituent",
			label_field="full_name",
			filters_json=frappe.as_json([["OT Language Child", "language", "=", language]]),
		)

		labels = [f["properties"]["label"] for f in get_layer_features(layer.name)["features"]]

		self.assertIn(speaker.full_name, labels)
		self.assertNotIn("Uninvolved Person", labels)

	def test_a_child_table_filter_matching_nobody_returns_nothing(self):
		"""The dangerous failure: resolving to an empty name list and then passing no
		filter at all, which would quietly plot every constituent on the map."""
		self._constituent("Not A Volunteer")
		language = self._language()

		layer = self._layer(
			layer_name="Test Empty Volunteers",
			source_doctype="OT Constituent",
			filters_json=frappe.as_json([["OT Language Child", "language", "=", language]]),
		)

		self.assertEqual(get_layer_features(layer.name)["features"], [])

	def _language(self):
		name = "Test Map Layer Language"

		if not frappe.db.exists("OT Language", name):
			frappe.get_doc({"doctype": "OT Language", "language": name}).insert()

		return name

	def _constituent(self, full_name, languages=None):
		first_name, _, last_name = full_name.partition(" ")
		address = self._address(f"{abs(hash(full_name)) % 9000} Constituent St")

		doc = frappe.get_doc(
			{
				"doctype": "OT Constituent",
				"first_name": first_name,
				"last_name": last_name,
				"address": address.name,
			}
		)

		for language in languages or []:
			doc.append("other_languages", {"language": language})

		return doc.insert()

	def test_reading_a_layer_requires_permission(self):
		layer = self._layer()
		user = self._user_without_roles()

		frappe.set_user(user)

		with self.assertRaises(frappe.PermissionError):
			get_layer_features(layer.name)

	def _user_without_roles(self):
		email = "test-map-layer-nobody@example.com"

		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "No Roles",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)

		return email

	# -- validation ---------------------------------------------------------------

	def test_a_doctype_without_coordinates_is_rejected(self):
		"""Better to refuse at save time than to show an empty layer nobody can explain."""
		self.assertNotIn("OT Walk List", get_mappable_doctypes())

		with self.assertRaises(frappe.ValidationError):
			self._layer(source_doctype="OT Walk List")

	def test_layers_come_back_in_their_display_order(self):
		"""The shared default stack. A viewer's own reordering is applied on top of this
		in the browser, so it must arrive sorted rather than alphabetical."""
		from organizer_toolkit.map_layers import get_layers

		self._layer(layer_name="Test Zzz On Top", display_order=1)
		self._layer(layer_name="Test Aaa Underneath", display_order=99)

		ordered = [
			row.layer_name for row in get_layers() if row.layer_name.startswith("Test ")
		]

		self.assertEqual(ordered, ["Test Zzz On Top", "Test Aaa Underneath"])

	def test_mappable_doctypes_covers_the_geocoded_ones(self):
		"""OT Constituent qualifies through a location fetched from its address, which is
		what lets people be mapped without geocoding them a second time."""
		mappable = get_mappable_doctypes()

		for doctype in ("OT Address", "OT Canvass Attempt", "OT Canvass Zone", "OT Constituent"):
			self.assertIn(doctype, mappable)

	def test_an_unknown_label_field_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._layer(label_field="not_a_field")

	def test_style_values_are_clamped(self):
		layer = self._layer(fill_opacity=5, marker_size=0, line_weight=-3)

		self.assertEqual(layer.fill_opacity, 1)
		self.assertEqual(layer.marker_size, 6)
		self.assertEqual(layer.line_weight, 0)

	def test_switching_to_a_file_clears_the_doctype_filters(self):
		"""A leftover filter naming OT Address columns would silently do nothing."""
		url = self._site_file("test_map_layer_switch.csv", CSV_CONTENT)
		layer = self._layer(filters_json='[["OT Address","city","=","Philadelphia"]]')

		layer.source_type = "File"
		layer.source_file = url
		layer.save()

		self.assertIsNone(layer.source_doctype)
		self.assertEqual(layer.filters_json, "[]")

	# -- file-backed layers -------------------------------------------------------

	def test_csv_columns_are_detected_from_the_header(self):
		"""target_lots.csv uses lat/lng, not latitude/longitude."""
		url = self._site_file("test_map_layer_lots.csv", CSV_CONTENT)

		layer = self._layer(layer_name="Test Lots", source_type="File", source_file=url)

		self.assertEqual(layer.latitude_column, "lat")
		self.assertEqual(layer.longitude_column, "lng")
		self.assertEqual(layer.label_column, "location")

	def test_a_hand_set_column_survives_the_next_save(self):
		"""Setting a column by hand is a correction of the guess, not an input to it."""
		url = self._site_file("test_map_layer_owner.csv", CSV_CONTENT)

		layer = self._layer(
			layer_name="Test Owner Label",
			source_type="File",
			source_file=url,
			label_column="owner_1",
		)
		layer.save()

		self.assertEqual(layer.label_column, "owner_1")

	def test_csv_layer_reads_points(self):
		url = self._site_file("test_map_layer_points.csv", CSV_CONTENT)
		layer = self._layer(layer_name="Test CSV Points", source_type="File", source_file=url)

		features = get_layer_features(layer.name)["features"]

		self.assertEqual(len(features), 2)
		self.assertEqual(features[0]["properties"]["label"], "1725 N 26TH ST")
		# GeoJSON wants longitude first.
		self.assertEqual(features[0]["geometry"]["coordinates"], [-75.176942, 39.981772])

	def test_geojson_file_layer_passes_features_through(self):
		url = self._site_file("test_map_layer_zones.geojson", GEOJSON_CONTENT)
		layer = self._layer(layer_name="Test GeoJSON", source_type="File", source_file=url)

		features = get_layer_features(layer.name)["features"]

		self.assertEqual(len(features), 1)
		self.assertEqual(features[0]["geometry"]["type"], "Polygon")
		self.assertEqual(features[0]["properties"]["label"], "Zone 9: Sunday")

	def test_max_features_truncates_and_says_so(self):
		"""A layer of thousands of pins locks up the map; the client shows the warning."""
		url = self._site_file("test_map_layer_capped.csv", CSV_CONTENT)
		layer = self._layer(
			layer_name="Test Capped", source_type="File", source_file=url, max_features=1
		)

		result = get_layer_features(layer.name)

		self.assertEqual(len(result["features"]), 1)
		self.assertEqual(result["total"], 2)
		self.assertTrue(result["truncated"])

	def test_a_file_path_cannot_escape_the_site(self):
		"""basename() is what stops a hand-typed path walking out of private/files.
		The column detection resolves the path during validate, so this never saves."""
		with self.assertRaises(frappe.ValidationError):
			self._layer(
				layer_name="Test Traversal",
				source_type="File",
				source_file="/private/files/../../../../etc/passwd",
			)

	def test_a_disabled_layer_returns_nothing(self):
		url = self._site_file("test_map_layer_off.csv", CSV_CONTENT)
		layer = self._layer(
			layer_name="Test Disabled", source_type="File", source_file=url, enabled=0
		)

		self.assertEqual(get_layer_features(layer.name)["features"], [])
