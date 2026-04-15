# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import today


class OTConstituent(Document):
	def validate(self):
		if self.mobile_phone == "+1-":
			self.mobile_phone = None

		if self.home_phone == "+1-":
			self.home_phone = None

	def before_save(self):
		# We set this here since virtual fields do not work with
		#   View Settings -> Title Field as of 2025-08-26
		self.full_name = (
			f"{self.first_name}"
			+ ((' "' + self.preferred_name + '"') if self.preferred_name else "")
			+ ((" " + self.last_name) if self.last_name else "")
		)

	def autoname(self):
		date_str = today().replace("-", "")
		month_str = date_str[:6]
		counter = getseries(f"CNST-{month_str}-", 5)
		number = counter.split("-")[-1]
		self.name = f"CNST-{date_str}-{number}"
