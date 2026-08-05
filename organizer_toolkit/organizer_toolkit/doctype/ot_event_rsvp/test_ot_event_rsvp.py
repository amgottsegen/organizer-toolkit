# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from organizer_toolkit.organizer_toolkit.doctype.ot_event_rsvp.ot_event_rsvp import (
	constituents_for_event,
)

VOLUNTEER = "test-rsvp-volunteer@example.com"


class TestOTEventRSVP(FrappeTestCase):
	"""RSVPs were a child table of OT Constituent, which meant recording one required
	write access to the person's entire record. That is why OT Volunteer could edit every
	constituent in the system. Promoting them is what closes that."""

	def setUp(self):
		self.event = frappe.get_doc(
			{
				"doctype": "OT Event",
				"event_name": "Test RSVP Event",
				"event_start": add_to_date(now_datetime(), days=7),
			}
		).insert()
		self.constituent = self._constituent("Rsvp Tester")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _constituent(self, full_name):
		first_name, _, last_name = full_name.partition(" ")

		return frappe.get_doc(
			{"doctype": "OT Constituent", "first_name": first_name, "last_name": last_name}
		).insert()

	def _rsvp(self, **kwargs):
		defaults = {
			"doctype": "OT Event RSVP",
			"constituent": self.constituent.name,
			"event": self.event.name,
		}
		defaults.update(kwargs)

		return frappe.get_doc(defaults).insert()

	def _volunteer(self):
		if not frappe.db.exists("User", VOLUNTEER):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": VOLUNTEER,
					"first_name": "RSVP Volunteer",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			user.add_roles("OT Volunteer")

		return VOLUNTEER

	# -- the shape --------------------------------------------------------------

	def test_an_rsvp_is_a_record_of_its_own(self):
		rsvp = self._rsvp(rsvp="Yes")

		self.assertEqual(rsvp.constituent, self.constituent.name)
		self.assertEqual(rsvp.constituent_name, self.constituent.full_name)

	def test_one_rsvp_per_person_per_event(self):
		"""Nothing enforced this as a child table and the data drifted -- 20 of 1057 rows
		were duplicates."""
		self._rsvp(rsvp="Yes")

		with self.assertRaises(frappe.ValidationError):
			self._rsvp(rsvp="No")

	def test_a_second_person_can_rsvp_to_the_same_event(self):
		self._rsvp()
		other = self._constituent("Second Guest")

		self._rsvp(constituent=other.name)

		self.assertEqual(len(constituents_for_event(self.event.name)), 2)

	# -- the filtering the UI depends on ----------------------------------------

	def test_constituents_for_event_narrows_by_answer(self):
		"""Frappe cannot filter a list view across a reverse link, so the constituent
		list resolves this to names and applies `name in (...)`."""
		yes = self._rsvp(rsvp="Yes")
		no_constituent = self._constituent("Declined Guest")
		self._rsvp(constituent=no_constituent.name, rsvp="No")

		saying_yes = constituents_for_event(self.event.name, rsvp="Yes")

		self.assertEqual(saying_yes, [yes.constituent])

	def test_constituents_for_event_narrows_by_attendance(self):
		self._rsvp(rsvp="Yes", attended=1)
		absent = self._constituent("Absent Guest")
		self._rsvp(constituent=absent.name, rsvp="Yes")

		self.assertEqual(constituents_for_event(self.event.name, attended=1), [self.constituent.name])

	def test_an_event_nobody_answered_returns_nothing(self):
		self.assertEqual(constituents_for_event(self.event.name), [])

	# -- what the promotion was for ---------------------------------------------

	def test_a_volunteer_can_rsvp_without_editing_the_constituent(self):
		"""The whole point. Before promotion this needed write on OT Constituent,
		because a child table inherits its parent's permissions."""
		frappe.set_user(self._volunteer())

		self.assertTrue(frappe.has_permission("OT Event RSVP", "create"))
		self.assertFalse(
			frappe.has_permission("OT Constituent", "write", doc=self.constituent.name),
			"a volunteer should no longer need write on the whole person",
		)

		rsvp = self._rsvp(rsvp="Yes")

		self.assertEqual(rsvp.owner, VOLUNTEER)

	def test_a_volunteer_cannot_edit_someone_elses_rsvp(self):
		rsvp = self._rsvp(rsvp="Yes")

		frappe.set_user(self._volunteer())

		self.assertFalse(frappe.has_permission("OT Event RSVP", "write", doc=rsvp.name))

	def test_a_volunteer_can_edit_their_own_rsvp(self):
		frappe.set_user(self._volunteer())
		rsvp = self._rsvp(rsvp="Maybe")

		rsvp.rsvp = "Yes"
		rsvp.save()

		self.assertEqual(frappe.db.get_value("OT Event RSVP", rsvp.name, "rsvp"), "Yes")

	def test_a_volunteer_can_still_create_a_constituent_at_the_door(self):
		"""Read all, create, edit own -- the same shape as doorknocks."""
		frappe.set_user(self._volunteer())

		constituent = self._constituent("Met At The Door")
		constituent.mobile_phone = "+1-215-555-0100"
		constituent.save()

		self.assertEqual(constituent.owner, VOLUNTEER)

	def test_a_volunteer_cannot_edit_a_constituent_they_did_not_add(self):
		frappe.set_user(self._volunteer())

		self.assertFalse(
			frappe.has_permission("OT Constituent", "write", doc=self.constituent.name)
		)

	def test_the_constituent_no_longer_carries_engagement_child_tables(self):
		"""A child table has no permissions of its own. Any that come back here would
		quietly reopen write access to the whole person."""
		tables = [
			field.fieldname
			for field in frappe.get_meta("OT Constituent").fields
			if field.fieldtype in ("Table", "Table MultiSelect")
		]

		self.assertNotIn("event_rsvps", tables)
		self.assertNotIn("volunteers_for", tables)
