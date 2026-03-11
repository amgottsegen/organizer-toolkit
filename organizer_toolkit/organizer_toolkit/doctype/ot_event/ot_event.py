# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date


class OTEvent(Document):
	def validate(self):
		self.event_end = add_to_date(self.event_start, seconds=self.event_duration)

	pass
