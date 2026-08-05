# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document


class OTVolunteerInterest(Document):
	def validate(self):
		self.check_for_duplicate()

	def check_for_duplicate(self):
		"""One record per person per activity.

		Saying "yes, I'll help knock doors" twice is one fact, not two -- and a canvasser
		asking the same question at a later visit should not create a second row.
		"""
		filters = {"constituent": self.constituent, "activity": self.activity}

		if not self.is_new():
			filters["name"] = ("!=", self.name)

		if frappe.db.exists("OT Volunteer Interest", filters):
			frappe.throw(
				_("{0} is already recorded as willing to help with {1}.").format(
					self.constituent_name or self.constituent, self.activity
				),
				title=_("Already Recorded"),
			)
