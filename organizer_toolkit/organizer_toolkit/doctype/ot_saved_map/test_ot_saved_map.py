# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import frappe
from frappe.tests.utils import FrappeTestCase

from organizer_toolkit.map_layers import get_saved_map, get_saved_maps, save_current_view

PHILLY = (39.9895, -75.1460)


class TestOTSavedMap(FrappeTestCase):
	def setUp(self):
		self.top = self._layer("Test Map Top Layer")
		self.bottom = self._layer("Test Map Bottom Layer")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _layer(self, layer_name):
		return frappe.get_doc(
			{
				"doctype": "OT Map Layer",
				"layer_name": layer_name,
				"source_type": "DocType",
				"source_doctype": "OT Address",
			}
		).insert()

	def _saved_map(self, map_name="Test Saved View", layers=None, **kwargs):
		doc = frappe.get_doc({"doctype": "OT Saved Map", "map_name": map_name, **kwargs})

		for layer in layers or []:
			doc.append("layers", {"layer": layer})

		return doc.insert()

	def test_row_order_is_the_stacking_order(self):
		"""The child table's idx is the whole ordering mechanism -- first row on top."""
		saved = self._saved_map(layers=[self.top.name, self.bottom.name])

		self.assertEqual(
			get_saved_map(saved.name)["layers"], [self.top.name, self.bottom.name]
		)

	def test_a_layer_listed_twice_is_collapsed(self):
		"""Two positions in the stack means whichever applied last wins, so the table
		would not match what the map draws."""
		saved = self._saved_map(layers=[self.top.name, self.top.name, self.bottom.name])

		self.assertEqual(len(saved.layers), 2)

	def test_saving_a_view_captures_layers_centre_and_zoom(self):
		result = save_current_view(
			map_name="Test Captured View",
			layers=[self.bottom.name, self.top.name],
			center_latitude=PHILLY[0],
			center_longitude=PHILLY[1],
			zoom=16,
		)

		saved = get_saved_map(result["name"])

		self.assertEqual(saved["layers"], [self.bottom.name, self.top.name])
		self.assertEqual(saved["zoom"], 16)
		self.assertAlmostEqual(saved["center_latitude"], PHILLY[0], places=4)

	def test_saving_over_an_existing_name_replaces_its_layers(self):
		"""Re-saving is how you adjust a view, so the layer list must not accumulate."""
		save_current_view(map_name="Test Reused Name", layers=[self.top.name])
		save_current_view(map_name="Test Reused Name", layers=[self.bottom.name])

		self.assertEqual(get_saved_map("Test Reused Name")["layers"], [self.bottom.name])

	def test_saving_accepts_a_json_layer_list(self):
		"""frappe.call posts the array as a JSON string."""
		result = save_current_view(
			map_name="Test JSON Layers", layers=frappe.as_json([self.top.name])
		)

		self.assertEqual(result["layers"], 1)

	def test_zoom_is_clamped_to_what_leaflet_accepts(self):
		"""setView silently clamps out-of-range zoom, which reads as the saved map being
		broken rather than the number being wrong."""
		saved = self._saved_map(map_name="Test Silly Zoom", zoom=99)

		self.assertEqual(saved.zoom, 20)

	def test_half_a_centre_is_treated_as_no_centre(self):
		"""Latitude with no longitude would send the map to the Atlantic off Africa."""
		saved = self._saved_map(map_name="Test Half Centre", center_latitude=PHILLY[0])

		self.assertIsNone(saved.center_latitude)
		self.assertIsNone(saved.center_longitude)

	def test_a_disabled_map_is_not_offered(self):
		self._saved_map(map_name="Test Retired View", enabled=0)
		self._saved_map(map_name="Test Current View")

		names = [row.name for row in get_saved_maps()]

		self.assertIn("Test Current View", names)
		self.assertNotIn("Test Retired View", names)

	def test_a_volunteer_cannot_overwrite_someone_elses_view(self):
		"""Upserting on the name is convenient, but it must not become a way to take over
		a view an organizer set up."""
		self._saved_map(map_name="Test Organizer View", layers=[self.top.name])

		frappe.set_user(self._volunteer())

		with self.assertRaises(frappe.PermissionError):
			save_current_view(map_name="Test Organizer View", layers=[self.bottom.name])

	def test_a_volunteer_can_save_their_own_view(self):
		frappe.set_user(self._volunteer())

		result = save_current_view(map_name="Test Volunteer View", layers=[self.top.name])

		self.assertEqual(result["layers"], 1)

	def _volunteer(self):
		email = "test-saved-map-volunteer@example.com"

		if not frappe.db.exists("User", email):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Saved Map Volunteer",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			user.add_roles("OT Volunteer")

		return email
