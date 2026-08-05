# Copyright (c) 2026, CREATE Lab and Contributors
# See license.txt
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from organizer_toolkit.address_utils import build_location_geojson
from organizer_toolkit.organizer_toolkit.doctype.ot_canvass_zone.ot_canvass_zone import (
	find_zone,
	restamp_addresses,
)


def square(west, south, east, north):
	"""A rectangular boundary, as the Geolocation field stores it."""
	return frappe.as_json(
		{
			"type": "FeatureCollection",
			"features": [
				{
					"type": "Feature",
					"properties": {},
					"geometry": {
						"type": "Polygon",
						"coordinates": [
							[
								[west, south],
								[east, south],
								[east, north],
								[west, north],
								[west, south],
							]
						],
					},
				}
			],
		}
	)


# Deliberately nowhere near the real zones on the site. Tests run against the live
# database, so fixtures drawn over Strawberry Mansion would be claimed by whichever
# actual boundary happens to cover them -- and would start failing the day someone
# redrew it.
WEST_BLOCK = square(-75.300, 39.900, -75.290, 39.910)
EAST_BLOCK = square(-75.280, 39.900, -75.270, 39.910)

INSIDE_WEST = (39.905, -75.295)
INSIDE_EAST = (39.905, -75.275)
NOWHERE = (40.500, -76.500)


class TestCanvassZoneAssignment(FrappeTestCase):
	"""A zone is a shape, so which doors belong to it is derived, never typed.

	Deriving it from the address rather than from the walk list is the point: most
	doorknocks are not logged against a walk list, so a fetch through that link would
	leave the zone filter blank for the majority of them.
	"""

	def setUp(self):
		self.zone = self._zone("Test Zone West", WEST_BLOCK)

	def tearDown(self):
		frappe.db.rollback()

	def _zone(self, zone_name, boundary):
		# Saving a boundary queues a re-stamp of every address.
		with patch("frappe.enqueue"):
			return frappe.get_doc(
				{"doctype": "OT Canvass Zone", "zone_name": zone_name, "location": boundary}
			).insert()

	def _address(self, street, coords=None):
		with patch("frappe.enqueue"):
			return frappe.get_doc(
				{
					"doctype": "OT Address",
					"address_line_1": street,
					"city": "Philadelphia",
					"location": build_location_geojson(*coords) if coords else None,
				}
			).insert()

	def _walk_list(self, list_name, zone=None):
		return frappe.get_doc(
			{"doctype": "OT Walk List", "list_name": list_name, "zone": zone}
		).insert()

	def _attempt(self, address, walk_list=None):
		return frappe.get_doc(
			{
				"doctype": "OT Canvass Attempt",
				"address": address.name,
				"outcome": "No answer",
				"walk_list": walk_list,
			}
		).insert()

	def test_an_address_is_stamped_with_the_zone_it_falls_in(self):
		self.assertEqual(self._address("100 Inside West St", INSIDE_WEST).zone, self.zone.name)

	def test_an_address_outside_every_boundary_has_no_zone(self):
		self.assertIsNone(self._address("200 Nowhere Near St", NOWHERE).zone)

	def test_an_ungeocoded_address_has_no_zone(self):
		"""0/0 is the ungeocoded sentinel, and it is in nobody's zone."""
		address = self._address("300 Not Located St")

		self.assertIsNone(address.zone)
		self.assertIsNone(find_zone(address.latitude, address.longitude))

	def test_an_inactive_zone_claims_nothing(self):
		self.zone.is_active = 0
		with patch("frappe.enqueue"):
			self.zone.save()

		self.assertIsNone(self._address("400 Retired Zone St", INSIDE_WEST).zone)

	def test_a_doorknock_takes_its_zone_from_its_walk_list(self):
		"""Not from the address. The walk list is what the door was canvassed for, and it
		does not move when a boundary is redrawn."""
		address = self._address("500 Fetched St", INSIDE_WEST)
		walk_list = self._walk_list("Test Walk List West", zone=self.zone.name)

		self.assertEqual(self._attempt(address, walk_list.name).zone, self.zone.name)

	def test_a_doorknock_with_no_walk_list_has_no_zone(self):
		"""There is nothing on record about which turf it belonged to, and the address's
		current zone is a guess about today rather than a fact about then."""
		address = self._address("510 No List St", INSIDE_WEST)

		self.assertEqual(address.zone, self.zone.name, "the address itself is in the zone")
		self.assertIsNone(self._attempt(address).zone)

	def test_redrawing_a_boundary_leaves_recorded_doorknocks_alone(self):
		"""The whole reason the label comes from the walk list. A door knocked for Zone 3
		was knocked for Zone 3, whatever shape Zone 3 is next month."""
		address = self._address("600 Moved Boundary St", INSIDE_WEST)
		walk_list = self._walk_list("Test Walk List History", zone=self.zone.name)
		attempt = self._attempt(address, walk_list.name)

		self.assertEqual(attempt.zone, self.zone.name)

		# Redraw the zone so it no longer covers this door at all.
		self.zone.location = EAST_BLOCK
		with patch("frappe.enqueue"):
			self.zone.save()

		restamp_addresses()

		self.assertIsNone(
			frappe.db.get_value("OT Address", address.name, "zone"),
			"the address follows current geography",
		)
		self.assertEqual(
			frappe.db.get_value("OT Canvass Attempt", attempt.name, "zone"),
			self.zone.name,
			"the doorknock keeps the zone it was canvassed for",
		)

	def test_setting_a_walk_lists_zone_labels_doors_already_knocked(self):
		"""fetch_from copies once at save time, so doors worked before the zone was filled
		in would stay unlabelled without this."""
		address = self._address("700 Labelled Later St", INSIDE_WEST)
		walk_list = self._walk_list("Test Walk List Unzoned")
		attempt = self._attempt(address, walk_list.name)

		self.assertIsNone(attempt.zone)

		walk_list.zone = self.zone.name
		walk_list.save()

		self.assertEqual(
			frappe.db.get_value("OT Canvass Attempt", attempt.name, "zone"), self.zone.name
		)

	def test_restamping_is_idempotent(self):
		self._address("800 Settled St", INSIDE_WEST)
		restamp_addresses()

		self.assertEqual(restamp_addresses(), 0, "a second pass should change nothing")

	def test_overlapping_zones_resolve_the_same_way_every_time(self):
		"""Zones may overlap. Which one wins matters less than it not changing between
		runs, which would make a zone's door count drift for no reason."""
		self._zone("Test Zone Also West", WEST_BLOCK)

		address = self._address("900 Contested St", INSIDE_WEST)

		self.assertEqual(address.zone, "Test Zone Also West", "first by name")
		self.assertEqual(find_zone(*INSIDE_WEST), address.zone)
