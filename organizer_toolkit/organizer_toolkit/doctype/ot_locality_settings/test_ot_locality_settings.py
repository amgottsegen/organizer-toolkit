# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from organizer_toolkit.locality import (
	DEFAULTS,
	clear_locality_cache,
	find_district,
	get_district_boundaries_path,
	get_locality,
	get_parcel_lookup_url,
)


class TestLocality(FrappeTestCase):
	"""Guards the promise that nothing outside locality.py knows about Philadelphia.

	If these start failing after a change, some place-specific value has probably been
	hardcoded back into the app."""

	def tearDown(self):
		frappe.db.rollback()
		clear_locality_cache()

	def test_settings_drive_values(self):
		settings = frappe.get_single("OT Locality Settings")
		settings.default_city = "Baltimore"
		settings.save()

		self.assertEqual(get_locality("default_city"), "Baltimore")

	def test_blank_setting_falls_back_to_preset(self):
		"""An unset field must not surface as an empty string or a zero coordinate."""
		settings = frappe.get_single("OT Locality Settings")
		settings.default_city = ""
		settings.map_center_latitude = 0
		settings.save()

		self.assertEqual(get_locality("default_city"), DEFAULTS["default_city"])
		self.assertEqual(get_locality("map_center_latitude"), DEFAULTS["map_center_latitude"])

	def test_bundled_boundaries_used_when_nothing_uploaded(self):
		path = get_district_boundaries_path()

		self.assertTrue(os.path.exists(path), f"{path} should exist")
		self.assertTrue(path.endswith(".geojson"))

	def test_find_district_resolves_a_point_in_the_city(self):
		# 811 W Firth St, Philadelphia -- a real geocoded address from the dataset.
		self.assertIsNotNone(find_district(39.99026, -75.14601))

	def test_find_district_returns_none_outside_the_boundaries(self):
		# Null Island: the 0/0 sentinel an ungeocoded address stores.
		self.assertIsNone(find_district(0, 0))

	def test_parcel_lookup_url_uses_the_template(self):
		url = get_parcel_lookup_url("1423 S 52nd St")

		self.assertIn("1423", url)
		self.assertNotIn("{address}", url)
		self.assertNotIn(" ", url, "address must be URL-encoded")

	def test_parcel_lookup_disabled_when_template_blank(self):
		settings = frappe.get_single("OT Locality Settings")
		settings.parcel_lookup_url = ""
		settings.save()
		# Blank means "this city has no property-record site", not "use Philadelphia's".
		DEFAULTS_BACKUP = DEFAULTS["parcel_lookup_url"]
		DEFAULTS["parcel_lookup_url"] = ""
		try:
			self.assertIsNone(get_parcel_lookup_url("1423 S 52nd St"))
		finally:
			DEFAULTS["parcel_lookup_url"] = DEFAULTS_BACKUP

	def test_labels_reach_the_doctype_meta(self):
		"""Quick Entry and list views read meta, not the settings doc -- the Property
		Setters generated on save are what make the configured labels actually show."""
		settings = frappe.get_single("OT Locality Settings")
		settings.parcel_id_label = "Tax Parcel Number"
		settings.save()

		frappe.clear_cache(doctype="OT Address")
		label = frappe.get_meta("OT Address").get_field("municipal_parcel_id").label

		self.assertEqual(label, "Tax Parcel Number")

	def test_city_default_reaches_the_doctype_meta(self):
		settings = frappe.get_single("OT Locality Settings")
		settings.default_city = "Camden"
		settings.save()

		frappe.clear_cache(doctype="OT Address")
		default = frappe.get_meta("OT Address").get_field("city").default

		self.assertEqual(default, "Camden")
