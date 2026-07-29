# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from organizer_toolkit.locality import get_locality
from organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address import find_or_create_address

# Attribution deliberately rides on the built-in `owner` field rather than a separate
# "canvasser" Link. The volunteer permission rows key on if_owner, so a second editable
# field could disagree with the permission boundary and misattribute a knock.


ANSWERED = "Answered"


class OTCanvassAttempt(Document):
	def validate(self):
		self.infer_outcome()

		if not self.canvassed_on:
			self.canvassed_on = now_datetime()

		# The browser sends Datetime fields as strings, so this has to be coerced before
		# comparing -- otherwise saving from the form raises TypeError on str > datetime.
		if get_datetime(self.canvassed_on) > now_datetime():
			frappe.throw(_("Canvassed On cannot be in the future."))

		if not self.follow_up_needed:
			self.follow_up_notes = None

		self.validate_constituent_matches_address()

	def on_update(self):
		"""Push what was captured at the door out to the records that own it.

		The canvass attempt stays the account of one conversation; the petition
		signature, the RSVP and the constituent's own volunteering list are where that
		information actually lives. Every step is idempotent, because on_update runs on
		each save and re-saving a doorknock must not record the same thing twice.
		"""
		if not self.constituent:
			return

		self.record_petition_signature()
		self.record_event_rsvp()
		self.sync_volunteer_activities()

	def record_petition_signature(self):
		if not self.petition_signed:
			return

		if frappe.db.exists(
			"OT Petition Signature",
			{"constituent": self.constituent, "petition": self.petition_signed},
		):
			return

		frappe.get_doc(
			{
				"doctype": "OT Petition Signature",
				"constituent": self.constituent,
				"petition": self.petition_signed,
				"signed_on": get_datetime(self.canvassed_on or now_datetime()).date(),
				"source": "Doorknocking",
			}
		).insert()

	def record_event_rsvp(self):
		if not self.event_rsvp:
			return

		# OT Event RSVP is still a child table of OT Constituent, so this appends a row
		# rather than inserting a record. Phase 4 promotes it to a standalone doctype;
		# this method is the thing that changes then.
		constituent = frappe.get_doc("OT Constituent", self.constituent)

		if any(row.event == self.event_rsvp for row in constituent.event_rsvps):
			return

		row = constituent.append("event_rsvps")
		row.event = self.event_rsvp
		row.origin = "Doorknocking"
		constituent.save()

	def sync_volunteer_activities(self):
		if not self.volunteers_for:
			return

		constituent = frappe.get_doc("OT Constituent", self.constituent)
		existing = {row.activity for row in constituent.volunteers_for}
		added = False

		for row in self.volunteers_for:
			if row.activity and row.activity not in existing:
				constituent.append("volunteers_for", {"activity": row.activity})
				added = True

		if added:
			constituent.save()

	def infer_outcome(self):
		"""Default to Answered when a constituent was recorded.

		Linking a person is only possible if somebody came to the door, so leaving the
		outcome blank in that case is a data-entry slip rather than a real state. Fills
		only when blank -- "Not interested" also implies an answer, and an explicit
		choice must never be overwritten.

		This runs in validate(), which Frappe calls before the mandatory-field check
		(document.py: run_before_save_methods then _validate), so `outcome` can stay
		required and still be satisfied by inference on API and import paths.
		"""
		if not self.outcome and self.constituent:
			self.outcome = ANSWERED

	def validate_constituent_matches_address(self):
		"""Warn when the linked person does not live at the door being logged.

		Not an error: canvassers legitimately meet people away from their registered
		address, and blocking the save would lose the visit entirely.
		"""
		if not self.constituent or not self.address:
			return

		constituent_address = frappe.db.get_value("OT Constituent", self.constituent, "address")

		if constituent_address and constituent_address != self.address:
			frappe.msgprint(
				_("Note: {0} is registered at a different address.").format(
					frappe.bold(self.constituent)
				),
				indicator="orange",
				alert=True,
			)


@frappe.whitelist()
def resolve_address(address_line_1, city=None, state=None, postal_code=None):
	"""Find or create the OT Address for a street a canvasser typed or tapped.

	Falls back to the configured locality for city and state. That matters for
	deduplication, not convenience: a street saved with no city produces a different
	address key than the same street saved with one, so the same door would end up as
	two records depending on how it was entered.
	"""
	locality = get_locality()

	address = find_or_create_address(
		address_line_1=address_line_1,
		city=city or locality["default_city"],
		state=state or locality["default_state"],
		postal_code=postal_code,
	)

	if not address:
		frappe.throw(_("A street address is required."))

	return {"name": address.name, "address_line_1": address.address_line_1}


@frappe.whitelist()
def log_visit(
	address_line_1,
	outcome,
	city=None,
	state=None,
	postal_code=None,
	address_line_2=None,
	notes=None,
	constituent=None,
):
	"""Create an address (or reuse the matching one) and log a visit against it.

	The single call field entry needs: a canvasser typing a house number on a block
	should not have to create the address first, then find it again to log the knock.
	Deduplication happens on the normalized address key, so re-entering a door that
	already exists attaches to the existing record instead of creating a twin.
	"""
	address = find_or_create_address(
		address_line_1=address_line_1,
		address_line_2=address_line_2,
		city=city,
		state=state,
		postal_code=postal_code,
	)

	if not address:
		frappe.throw(_("A street address is required to log a visit."))

	attempt = frappe.get_doc(
		{
			"doctype": "OT Canvass Attempt",
			"address": address.name,
			"constituent": constituent,
			"outcome": outcome,
			"notes": notes,
			"canvassed_on": now_datetime(),
		}
	).insert()

	return {
		"canvass_attempt": attempt.name,
		"address": address.name,
		"street_address": address.address_line_1,
	}


@frappe.whitelist()
def get_address_history(address):
	"""Prior visits to this door, so a canvasser can see it was already knocked."""
	return frappe.get_list(
		"OT Canvass Attempt",
		filters={"address": address},
		fields=["name", "canvassed_on", "outcome", "notes", "owner"],
		order_by="canvassed_on desc",
		limit_page_length=10,
	)
