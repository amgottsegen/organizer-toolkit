# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime


class TestOTEvent(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_event_saves_without_a_duration(self):
		"""Duration is optional on the form, so leaving it blank must not crash.

		add_to_date(seconds=None) raises a TypeError, which made saving any event
		without a duration impossible.
		"""
		event = frappe.get_doc(
			{
				"doctype": "OT Event",
				"event_name": "Event With No Duration",
				"event_start": add_to_date(now_datetime(), days=3),
			}
		).insert()

		self.assertIsNone(event.event_end)

	def test_event_end_is_derived_from_duration(self):
		start = add_to_date(now_datetime(), days=3)
		event = frappe.get_doc(
			{
				"doctype": "OT Event",
				"event_name": "Event With Duration",
				"event_start": start,
				"event_duration": 3600,
			}
		).insert()

		self.assertEqual(event.event_end, add_to_date(start, seconds=3600))

	def test_event_saves_without_a_start(self):
		event = frappe.get_doc({"doctype": "OT Event", "event_name": "Undated Event"}).insert()

		self.assertIsNone(event.event_end)
