# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class OTAssessment(Document):
	def autoname(self):
		# We set this here since virtual fields do not work with
		#   View Settings -> Title Field as of 2025-08-26
		self.name = f"{self.level}" + " - " + f"{self.label}"
