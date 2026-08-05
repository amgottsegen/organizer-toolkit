# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import frappe
from frappe.tests.utils import FrappeTestCase


class TestOTVolunteerInterest(FrappeTestCase):
	"""The other half of the promotion. Leaving `volunteers_for` as a child table on the
	constituent would have kept write access to the whole person necessary, whatever
	happened to the RSVPs."""

	def setUp(self):
		self.constituent = frappe.get_doc(
			{"doctype": "OT Constituent", "first_name": "Interest", "last_name": "Tester"}
		).insert()
		self.activity = self._activity("Test Interest Activity")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _activity(self, name):
		if not frappe.db.exists("OT Activity", name):
			frappe.get_doc({"doctype": "OT Activity", "activity_name": name}).insert()

		return name

	def _interest(self, **kwargs):
		defaults = {
			"doctype": "OT Volunteer Interest",
			"constituent": self.constituent.name,
			"activity": self.activity,
		}
		defaults.update(kwargs)

		return frappe.get_doc(defaults).insert()

	def test_an_interest_records_who_and_what(self):
		interest = self._interest()

		self.assertEqual(interest.constituent_name, self.constituent.full_name)
		self.assertEqual(interest.source, "Doorknocking")

	def test_the_same_offer_is_not_recorded_twice(self):
		"""Asking again at a later visit is one fact, not two."""
		self._interest()

		with self.assertRaises(frappe.ValidationError):
			self._interest()

	def test_a_person_can_offer_to_help_with_several_things(self):
		self._interest()
		self._interest(activity=self._activity("Test Second Activity"))

		self.assertEqual(
			frappe.db.count("OT Volunteer Interest", {"constituent": self.constituent.name}), 2
		)

	def test_the_canvass_attempt_child_table_survives(self):
		"""Only the constituent-side copy became records. On a doorknock the child table
		is the right shape -- the canvasser already owns the attempt they are filling in,
		so it needs no extra permission."""
		meta = frappe.get_meta("OT Canvass Attempt")

		self.assertTrue(meta.has_field("volunteers_for"))
		self.assertEqual(meta.get_field("volunteers_for").options, "OT Activity Child")
