# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import add_to_date


class OTEvent(Document):
	def validate(self):
		self.set_event_end()

	def set_event_end(self):
		"""Derive the end time from start plus duration.

		Both fields are optional on the form, but `add_to_date` raises a TypeError on a
		None duration -- so saving an event without one used to crash outright. Guard
		instead and simply leave the end time unset.
		"""
		if not self.event_start or not self.event_duration:
			self.event_end = None
			return

		self.event_end = add_to_date(self.event_start, seconds=self.event_duration)
