# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import frappe
from frappe.tests.utils import FrappeTestCase

from organizer_toolkit.address_utils import build_address_key, normalize_street, normalize_unit


class TestAddressKey(FrappeTestCase):
	"""The dedupe key is the one place where a silent logic error corrupts data rather
	than throwing -- a key that is too loose merges two real doors into one record, and
	one that is too strict splits a single door's canvass history across duplicates."""

	def test_spelling_variants_collapse(self):
		"""What a canvasser types and what city records say must reach the same key."""
		variants = [
			("1423 S 52nd St", "Philadelphia", "19143"),
			("1423 South 52nd Street", "philadelphia", "19143"),
			("1423 S 52ND ST", "PHILADELPHIA", "19143-1234"),
			("1423 s. 52nd st.", "Philadelphia", "19143"),
		]
		keys = {build_address_key(line, None, city, postal) for line, city, postal in variants}

		self.assertEqual(len(keys), 1, f"expected one key, got {keys}")

	def test_distinct_addresses_stay_distinct(self):
		neighbour_a = build_address_key("1423 S 52nd St", None, "Philadelphia", "19143")
		neighbour_b = build_address_key("1425 S 52nd St", None, "Philadelphia", "19143")

		self.assertNotEqual(neighbour_a, neighbour_b)

	def test_units_are_distinct(self):
		"""Two apartments at one street address are two separate doors."""
		unit_a = build_address_key("55 Main St", "Apt 2B", "Philadelphia", "19100")
		unit_b = build_address_key("55 Main St", "Apt 3B", "Philadelphia", "19100")

		self.assertNotEqual(unit_a, unit_b)

	def test_unit_designators_normalize(self):
		keys = {normalize_unit(v) for v in ["Apt. 2B", "#2b", "Unit 2B", "APARTMENT 2b"]}

		self.assertEqual(keys, {"2b"})

	def test_saint_prefix_is_not_expanded_as_street_type(self):
		"""'St' leading a street name is Saint, not Street -- only the trailing token is
		a street type. Expanding both would collapse unrelated addresses."""
		self.assertEqual(normalize_street("100 St James Pl"), "100 st james place")

	def test_trailing_directional(self):
		self.assertEqual(normalize_street("700 Main St NW"), "700 main street northwest")

	def test_blank_street_yields_no_key(self):
		"""An address with no street cannot be deduplicated, so it must not get a key."""
		self.assertEqual(build_address_key("", None, "Philadelphia", "19100"), "")


class TestOTAddress(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _make(self, **kwargs):
		defaults = {
			"doctype": "OT Address",
			"address_line_1": "1423 S 52nd St",
			"city": "Philadelphia",
			"state": "PA",
			"postal_code": "19143",
		}
		defaults.update(kwargs)

		return frappe.get_doc(defaults).insert()

	def test_address_key_is_set_on_save(self):
		doc = self._make()

		self.assertEqual(doc.address_key, "1423 south 52nd street||philadelphia|19143")

	def test_duplicate_is_rejected_with_a_usable_message(self):
		self._make()

		with self.assertRaises(frappe.ValidationError):
			self._make(address_line_1="1423 South 52nd Street")

	def test_latitude_longitude_derived_from_location(self):
		doc = self._make(
			location=frappe.as_json(
				{
					"type": "FeatureCollection",
					"features": [
						{
							"type": "Feature",
							"geometry": {"type": "Point", "coordinates": [-75.1460133, 39.9902584]},
							"properties": {},
						}
					],
				}
			)
		)

		self.assertAlmostEqual(doc.latitude, 39.9902584, places=6)
		self.assertAlmostEqual(doc.longitude, -75.1460133, places=6)

	def test_find_or_create_reuses_existing(self):
		from organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address import (
			find_or_create_address,
		)

		first = self._make()
		second = find_or_create_address("1423 s. 52nd st.", None, "Philadelphia", "PA", "19143")

		self.assertEqual(first.name, second.name)


class TestVolunteerPermissions(FrappeTestCase):
	"""A volunteer must be able to log a door they knocked without being able to rewrite
	shared records. Guarded by a test because OT Constituent is governed by Custom
	DocPerm fixtures, which silently replace the permissions in the doctype JSON -- a
	role added only to the JSON would appear correct in source and grant nothing."""

	VOLUNTEER = "ot-volunteer-test@example.com"

	def setUp(self):
		if not frappe.db.exists("User", self.VOLUNTEER):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": self.VOLUNTEER,
					"first_name": "Test Volunteer",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			user.add_roles("OT Volunteer")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_volunteer_can_create_but_not_edit_addresses(self):
		frappe.set_user(self.VOLUNTEER)

		self.assertTrue(frappe.has_permission("OT Address", "create"))
		self.assertTrue(frappe.has_permission("OT Address", "read"))
		self.assertFalse(frappe.has_permission("OT Address", "write"))
		self.assertFalse(frappe.has_permission("OT Address", "delete"))

	def test_volunteer_cannot_delete_constituents(self):
		frappe.set_user(self.VOLUNTEER)

		self.assertTrue(frappe.has_permission("OT Constituent", "read"))
		self.assertFalse(frappe.has_permission("OT Constituent", "delete"))

	def test_organizer_reaches_every_toolkit_doctype(self):
		"""Staff organizers are meant to see everything in the toolkit.

		Guards against the easy mistake of adding a doctype and forgetting the role --
		which is exactly how OT Organizer originally ended up with no access to Events,
		Assessments, Languages, Constituent Types, Event Spaces or Resident Types.
		Child tables are excluded: they inherit their parent's permissions."""
		doctypes = frappe.get_all(
			"DocType",
			filters={"module": "Organizer Toolkit", "istable": 0},
			pluck="name",
		)
		self.assertTrue(doctypes, "expected some Organizer Toolkit doctypes")

		missing = [
			doctype
			for doctype in doctypes
			if not any(p.role == "OT Organizer" for p in frappe.get_meta(doctype).permissions)
		]

		self.assertEqual(missing, [], f"OT Organizer has no permissions on: {missing}")

	def test_no_custom_docperm_shadows_toolkit_doctypes(self):
		"""Permissions for doctypes this app owns must come from their doctype JSON.

		A single Custom DocPerm row replaces a doctype's whole permission list
		(frappe/model/meta.py, Meta.set_custom_permissions), so the array in source
		becomes dead code -- that is how adding OT Organizer to ot_constituent.json
		once appeared to work while granting nothing. Editing permissions in the desk
		UI recreates these rows, so this test is the tripwire for that happening."""
		toolkit_doctypes = frappe.get_all(
			"DocType", filters={"module": "Organizer Toolkit"}, pluck="name"
		)
		shadowed = frappe.get_all(
			"Custom DocPerm",
			filters={"parent": ["in", toolkit_doctypes]},
			distinct=True,
			pluck="parent",
		)

		self.assertEqual(
			shadowed,
			[],
			f"Custom DocPerm rows are overriding the doctype JSON for: {shadowed}. "
			"Move the intended permissions into the doctype JSON and delete these rows.",
		)

	def test_volunteer_can_read_link_target_doctypes(self):
		"""Link fields on the constituent form are unusable if the volunteer cannot read
		the target doctype -- the picker silently returns nothing."""
		frappe.set_user(self.VOLUNTEER)

		for doctype in ("OT Constituent Type", "OT Resident Type", "OT Language", "OT Assessment"):
			self.assertTrue(
				frappe.has_permission(doctype, "read"),
				f"OT Volunteer needs read on {doctype} for the link picker to work",
			)

	def test_organizer_has_full_access_to_constituents(self):
		"""Regression guard: OT Organizer lives in the Custom DocPerm fixture, not the
		doctype JSON. If it is ever added to only the JSON this fails."""
		organizer = "ot-organizer-test@example.com"

		if not frappe.db.exists("User", organizer):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": organizer,
					"first_name": "Test Organizer",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			user.add_roles("OT Organizer")

		frappe.set_user(organizer)

		for ptype in ("create", "read", "write", "delete"):
			self.assertTrue(
				frappe.has_permission("OT Constituent", ptype),
				f"OT Organizer should have {ptype} on OT Constituent",
			)
