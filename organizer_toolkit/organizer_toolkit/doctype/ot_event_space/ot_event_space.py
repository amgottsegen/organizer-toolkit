# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class OTEventSpace(Document):
	def validate(self):
		if self.contact_phone == "+1-":
			self.contact_phone = None
