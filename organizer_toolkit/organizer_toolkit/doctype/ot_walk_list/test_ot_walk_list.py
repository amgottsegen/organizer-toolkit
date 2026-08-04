# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from organizer_toolkit.address_utils import build_location_geojson
from organizer_toolkit.organizer_toolkit.doctype.ot_canvass_zone.ot_canvass_zone import (
	addresses_within,
)
from organizer_toolkit.organizer_toolkit.doctype.ot_walk_list.ot_walk_list import (
	create_from_addresses,
	get_progress,
	populate_from_zone,
)

# A small square around a point in Philadelphia, as the Geolocation field stores it.
ZONE_BOUNDARY = {
	"type": "FeatureCollection",
	"features": [
		{
			"type": "Feature",
			"properties": {},
			"geometry": {
				"type": "Polygon",
				"coordinates": [
					[
						[-75.150, 39.985],
						[-75.140, 39.985],
						[-75.140, 39.995],
						[-75.150, 39.995],
						[-75.150, 39.985],
					]
				],
			},
		}
	],
}

INSIDE = (39.990, -75.145)
OUTSIDE = (39.930, -75.200)


class TestWalkListAndZones(FrappeTestCase):
	def setUp(self):
		self.zone = frappe.get_doc(
			{
				"doctype": "OT Canvass Zone",
				"zone_name": "Test Zone Alpha",
				"day_of_week": "Monday",
				"location": frappe.as_json(ZONE_BOUNDARY),
			}
		).insert()

		# patch enqueue: creating an address otherwise queues a Nominatim lookup.
		with patch("frappe.enqueue"):
			self.inside = self._address("100 Inside Zone St", INSIDE)
			self.outside = self._address("200 Outside Zone St", OUTSIDE)

		self.walk_list = frappe.get_doc(
			{
				"doctype": "OT Walk List",
				"list_name": "Test Walk List",
				"zone": self.zone.name,
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def _address(self, street, coords):
		return frappe.get_doc(
			{
				"doctype": "OT Address",
				"address_line_1": street,
				"city": "Philadelphia",
				"location": build_location_geojson(*coords),
			}
		).insert()

	def test_zone_finds_only_addresses_inside_its_boundary(self):
		inside = addresses_within(self.zone.name)

		self.assertIn(self.inside.name, inside)
		self.assertNotIn(self.outside.name, inside)

	def test_zone_without_a_boundary_is_rejected(self):
		"""Silently returning nothing would look like a zone with no addresses."""
		bare = frappe.get_doc(
			{"doctype": "OT Canvass Zone", "zone_name": "Test Zone No Boundary"}
		).insert()

		with self.assertRaises(frappe.ValidationError):
			addresses_within(bare.name)

	def test_populate_from_zone_adds_the_addresses_inside(self):
		result = populate_from_zone(self.walk_list.name)
		doc = frappe.get_doc("OT Walk List", self.walk_list.name)
		listed = [row.address for row in doc.addresses]

		self.assertIn(self.inside.name, listed)
		self.assertNotIn(self.outside.name, listed)
		self.assertEqual(result["added"], len(listed))

	def test_populating_twice_does_not_duplicate_doors(self):
		"""Additive by design, so a canvasser must not be sent to one door twice."""
		populate_from_zone(self.walk_list.name)
		populate_from_zone(self.walk_list.name)

		doc = frappe.get_doc("OT Walk List", self.walk_list.name)
		listed = [row.address for row in doc.addresses]

		self.assertEqual(len(listed), len(set(listed)))

	def test_hand_added_duplicate_is_collapsed_on_save(self):
		doc = frappe.get_doc("OT Walk List", self.walk_list.name)
		doc.append("addresses", {"address": self.inside.name})
		doc.append("addresses", {"address": self.inside.name})
		doc.save()

		self.assertEqual(len([row.address for row in doc.addresses]), 1)

	def test_progress_is_derived_from_canvass_attempts(self):
		populate_from_zone(self.walk_list.name)

		before = get_progress(self.walk_list.name)
		self.assertEqual(before["knocked"], 0)
		self.assertTrue(before["total"])

		frappe.get_doc(
			{
				"doctype": "OT Canvass Attempt",
				"address": self.inside.name,
				"outcome": "No answer",
				"walk_list": self.walk_list.name,
			}
		).insert()

		after = get_progress(self.walk_list.name)
		self.assertEqual(after["knocked"], 1)
		self.assertNotIn(self.inside.name, after["remaining"])

	def test_a_visit_without_the_walk_list_does_not_count(self):
		"""Progress is scoped to this list, so an unrelated knock at the same door does
		not mark it done here."""
		populate_from_zone(self.walk_list.name)

		frappe.get_doc(
			{
				"doctype": "OT Canvass Attempt",
				"address": self.inside.name,
				"outcome": "No answer",
			}
		).insert()

		self.assertEqual(get_progress(self.walk_list.name)["knocked"], 0)

	def test_create_from_addresses_takes_the_selection_as_given(self):
		"""The list-view action: ticked doors become a route, geocoded or not."""
		result = create_from_addresses(
			addresses=[self.inside.name, self.outside.name],
			list_name="Selected Doors",
		)

		doc = frappe.get_doc("OT Walk List", result["name"])
		listed = [row.address for row in doc.addresses]

		self.assertEqual(result["total"], 2)
		self.assertIn(self.inside.name, listed)
		self.assertIn(self.outside.name, listed, "a door outside any zone is still a door")
		self.assertEqual(doc.list_name, "Selected Doors")

	def test_create_from_addresses_accepts_a_json_selection(self):
		"""frappe.call posts the array as a JSON string."""
		result = create_from_addresses(
			addresses=frappe.as_json([self.inside.name]),
			list_name="From JSON",
		)

		self.assertEqual(result["total"], 1)

	def test_create_from_addresses_collapses_repeats(self):
		result = create_from_addresses(
			addresses=[self.inside.name, self.inside.name],
			list_name="Repeated Door",
		)

		self.assertEqual(result["total"], 1)

	def test_create_from_addresses_rejects_an_empty_selection(self):
		"""An empty walk list looks like a finished one -- refuse rather than create it."""
		with self.assertRaises(frappe.ValidationError):
			create_from_addresses(addresses=[], list_name="Nothing Selected")

	def test_create_from_addresses_defaults_the_canvass_date(self):
		result = create_from_addresses(
			addresses=[self.inside.name], list_name="Undated", canvass_date=None
		)

		doc = frappe.get_doc("OT Walk List", result["name"])
		self.assertEqual(str(doc.canvass_date), frappe.utils.nowdate())

	def test_log_visit_attaches_to_the_walk_list(self):
		"""What rapid block entry relies on: the visit it creates must count toward the
		list the canvasser launched it from."""
		from organizer_toolkit.organizer_toolkit.doctype.ot_canvass_attempt.ot_canvass_attempt import (
			log_visit,
		)

		populate_from_zone(self.walk_list.name)

		with patch("frappe.enqueue"):
			result = log_visit(
				address_line_1="100 Inside Zone St",
				outcome="Answered",
				city="Philadelphia",
				walk_list=self.walk_list.name,
			)

		attempt = frappe.get_doc("OT Canvass Attempt", result["canvass_attempt"])

		self.assertEqual(attempt.walk_list, self.walk_list.name)
		self.assertEqual(attempt.address, self.inside.name, "should reuse the existing door")
		self.assertEqual(get_progress(self.walk_list.name)["knocked"], 1)
