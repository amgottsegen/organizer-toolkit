# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document


class OTPetitionSignature(Document):
	def validate(self):
		self.check_for_duplicate()

	def check_for_duplicate(self):
		"""One person signs a given petition once.

		Canvassers work the same block over weeks and will offer the same petition to
		someone who already signed it; without this the signature count quietly inflates.
		"""
		filters = {"constituent": self.constituent, "petition": self.petition}
		if not self.is_new():
			filters["name"] = ("!=", self.name)

		existing = frappe.db.get_value("OT Petition Signature", filters, "name")

		if existing:
			frappe.throw(
				_("{0} has already signed this petition ({1}).").format(
					frappe.bold(self.constituent_name or self.constituent),
					f'<a href="/app/ot-petition-signature/{existing}">{existing}</a>',
				),
				title=_("Already Signed"),
			)
