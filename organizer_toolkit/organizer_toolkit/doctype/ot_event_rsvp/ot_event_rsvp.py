# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document


class OTEventRSVP(Document):
	def validate(self):
		self.check_for_duplicate()

	def check_for_duplicate(self):
		"""One RSVP per person per event.

		As a child table nothing enforced this and the data drifted -- 20 of 1057 rows
		were duplicates, almost all of them empty placeholders sitting beside a real
		answer. Enforced here rather than as a unique index so the message can name the
		record to go and edit.
		"""
		filters = {"constituent": self.constituent, "event": self.event}

		if not self.is_new():
			filters["name"] = ("!=", self.name)

		existing = frappe.db.get_value("OT Event RSVP", filters, "name")

		if existing:
			frappe.throw(
				_("{0} already has an RSVP for this event: {1}.").format(
					self.constituent_name or self.constituent,
					f'<a href="/app/ot-event-rsvp/{existing}">{existing}</a>',
				),
				title=_("Duplicate RSVP"),
			)


@frappe.whitelist()
def constituents_for_event(event, rsvp=None, attended=None):
	"""Names of constituents with an RSVP to this event.

	Frappe cannot filter a list view across a reverse link -- db_query joins child tables
	on parent/parenttype and link fields forwards only -- so "constituents who said yes to
	this event" has to be resolved to a list of names and applied as `name in (...)`.
	That is what the Event filter button on the constituent list does.
	"""
	filters = {"event": event}

	if rsvp:
		filters["rsvp"] = rsvp

	if attended not in (None, ""):
		filters["attended"] = int(attended)

	return frappe.get_all(
		"OT Event RSVP",
		filters=filters,
		pluck="constituent",
		limit_page_length=0,
		distinct=True,
	)
