# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OTConstituent(Document):
	def validate(self):
		if self.mobile_phone == "+1-":
			self.mobile_phone = None

		if self.home_phone == "+1-":
			self.home_phone = None

	pass
