# Copyright (c) 2026, CREATE Lab and contributors
# See license.txt
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, now_datetime

from organizer_toolkit.organizer_toolkit.doctype.ot_canvass_attempt.ot_canvass_attempt import (
	get_address_history,
	log_visit,
	resolve_address,
)


class TestOTCanvassAttempt(FrappeTestCase):
	def setUp(self):
		self.address = frappe.get_doc(
			{
				"doctype": "OT Address",
				"address_line_1": "900 Test Canvass St",
				"city": "Philadelphia",
				"state": "PA",
				"postal_code": "19100",
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _attempt(self, **kwargs):
		defaults = {
			"doctype": "OT Canvass Attempt",
			"address": self.address.name,
			"outcome": "No answer",
		}
		defaults.update(kwargs)

		return frappe.get_doc(defaults).insert()

	def test_canvassed_on_defaults_to_now(self):
		attempt = self._attempt()

		self.assertIsNotNone(attempt.canvassed_on)

	def test_future_visits_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._attempt(canvassed_on=add_to_date(now_datetime(), days=1))

	def test_canvassed_on_accepts_a_string_from_the_form(self):
		"""The browser posts Datetime fields as strings, not datetime objects.

		Comparing a string against now_datetime() raises TypeError, so every save from
		the actual form failed while tests passing datetime objects stayed green.
		"""
		attempt = self._attempt(canvassed_on="2026-07-20 14:30:00")

		self.assertEqual(get_datetime(attempt.canvassed_on), get_datetime("2026-07-20 14:30:00"))

	def test_future_visits_rejected_when_sent_as_a_string(self):
		future = add_to_date(now_datetime(), days=1).strftime("%Y-%m-%d %H:%M:%S")

		with self.assertRaises(frappe.ValidationError):
			self._attempt(canvassed_on=future)

	def test_address_is_required(self):
		"""A visit with no door is unusable -- it cannot be deduplicated or mapped."""
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "OT Canvass Attempt", "outcome": "No answer"}).insert()

	def test_constituent_is_optional(self):
		"""Nobody answering is the most common outcome; it must still be loggable."""
		attempt = self._attempt(outcome="No answer")

		self.assertIsNone(attempt.constituent)

	def _constituent(self):
		return frappe.get_doc(
			{
				"doctype": "OT Constituent",
				"first_name": "Canvass",
				"last_name": "Subject",
				"address": self.address.name,
			}
		).insert()

	def test_outcome_inferred_as_answered_when_a_constituent_is_linked(self):
		"""You cannot record who you spoke to unless somebody answered the door."""
		attempt = self._attempt(outcome=None, constituent=self._constituent().name)

		self.assertEqual(attempt.outcome, "Answered")

	def test_inference_does_not_overwrite_an_explicit_outcome(self):
		"""'Not interested' also implies an answer -- the canvasser's choice wins."""
		attempt = self._attempt(outcome="Not interested", constituent=self._constituent().name)

		self.assertEqual(attempt.outcome, "Not interested")

	def test_outcome_still_required_without_a_constituent(self):
		"""Nothing to infer from, so the mandatory check must still bite."""
		with self.assertRaises(frappe.ValidationError):
			self._attempt(outcome=None)

	def test_follow_up_notes_cleared_when_flag_is_off(self):
		attempt = self._attempt(follow_up_needed=0, follow_up_notes="stale note")

		self.assertIsNone(attempt.follow_up_notes)

	def test_street_address_is_fetched_for_the_list_view(self):
		attempt = self._attempt()

		self.assertEqual(attempt.street_address, "900 Test Canvass St")

	def test_resolve_address_reuses_the_matching_door(self):
		"""The map deep-links with a street; it must attach to the existing address
		rather than creating a near-duplicate."""
		resolved = resolve_address("900 test canvass street")

		self.assertEqual(resolved["name"], self.address.name)

	def test_resolve_address_applies_locality_defaults(self):
		"""Without a city the address key would differ from the same door entered by
		hand, splitting one door across two records."""
		resolved = resolve_address("902 Test Canvass St")
		created = frappe.get_doc("OT Address", resolved["name"])

		self.assertEqual(created.city, "Philadelphia")
		self.assertEqual(created.state, "PA")

	def test_log_visit_creates_address_and_attempt_together(self):
		result = log_visit(
			address_line_1="904 Test Canvass St",
			outcome="Answered",
			city="Philadelphia",
			state="PA",
			postal_code="19100",
			notes="spoke with resident",
		)
		attempt = frappe.get_doc("OT Canvass Attempt", result["canvass_attempt"])

		self.assertEqual(attempt.outcome, "Answered")
		self.assertEqual(attempt.address, result["address"])
		self.assertEqual(attempt.notes, "spoke with resident")

	def test_log_visit_reuses_an_existing_address(self):
		before = frappe.db.count("OT Address")
		log_visit(address_line_1="900 Test Canvass St", outcome="Not interested", city="Philadelphia")

		self.assertEqual(frappe.db.count("OT Address"), before, "should not have created a twin")

	def test_address_history_is_most_recent_first(self):
		self._attempt(outcome="No answer", canvassed_on=add_to_date(now_datetime(), days=-3))
		self._attempt(outcome="Answered", canvassed_on=add_to_date(now_datetime(), days=-1))

		history = get_address_history(self.address.name)

		self.assertEqual(len(history), 2)
		self.assertEqual(history[0].outcome, "Answered")


class TestCanvassEscalation(FrappeTestCase):
	"""The Supporter and Member sections capture what was said at a door, then push it
	out to the records that own it. on_update fires on every save, so each of these has
	to be idempotent -- re-saving a doorknock must not sign the petition twice."""

	def setUp(self):
		self.address = frappe.get_doc(
			{"doctype": "OT Address", "address_line_1": "920 Escalation St", "city": "Philadelphia"}
		).insert()
		self.constituent = frappe.get_doc(
			{"doctype": "OT Constituent", "first_name": "Escalation", "last_name": "Tester"}
		).insert()
		self.petition = frappe.get_doc(
			{"doctype": "OT Petition", "petition_name": "Test Petition for Canvassing"}
		).insert()
		self.event = frappe.get_doc(
			{
				"doctype": "OT Event",
				"event_name": "Test Canvass Event",
				"event_start": add_to_date(now_datetime(), days=7),
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _attempt(self, **kwargs):
		defaults = {
			"doctype": "OT Canvass Attempt",
			"address": self.address.name,
			"outcome": "Answered",
			"constituent": self.constituent.name,
		}
		defaults.update(kwargs)

		return frappe.get_doc(defaults).insert()

	def test_petition_signature_records_from_a_string_datetime(self):
		"""Same string-vs-datetime trap: signed_on called .date() on canvassed_on, which
		raises AttributeError when the form supplied it as a string."""
		self._attempt(petition_signed=self.petition.name, canvassed_on="2026-07-20 14:30:00")

		signature = frappe.db.get_value(
			"OT Petition Signature",
			{"constituent": self.constituent.name, "petition": self.petition.name},
			"signed_on",
			as_dict=True,
		)

		self.assertEqual(str(signature.signed_on), "2026-07-20")

	def test_petition_signature_is_recorded(self):
		self._attempt(petition_signed=self.petition.name)

		self.assertTrue(
			frappe.db.exists(
				"OT Petition Signature",
				{"constituent": self.constituent.name, "petition": self.petition.name},
			)
		)

	def test_petition_signature_is_not_duplicated_on_resave(self):
		attempt = self._attempt(petition_signed=self.petition.name)
		attempt.notes = "edited after the fact"
		attempt.save()

		self.assertEqual(
			frappe.db.count(
				"OT Petition Signature",
				{"constituent": self.constituent.name, "petition": self.petition.name},
			),
			1,
		)

	def test_signing_the_same_petition_twice_is_rejected(self):
		"""Canvassers work a block repeatedly and will re-offer a signed petition."""
		self._attempt(petition_signed=self.petition.name)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "OT Petition Signature",
					"constituent": self.constituent.name,
					"petition": self.petition.name,
				}
			).insert()

	def test_event_rsvp_is_recorded_once(self):
		attempt = self._attempt(event_rsvp=self.event.name)
		attempt.notes = "second save"
		attempt.save()

		constituent = frappe.get_doc("OT Constituent", self.constituent.name)
		rsvps = [r for r in constituent.event_rsvps if r.event == self.event.name]

		self.assertEqual(len(rsvps), 1)
		self.assertEqual(rsvps[0].origin, "Doorknocking")

	def test_volunteer_activities_merge_into_the_constituent(self):
		attempt = self._attempt(
			volunteers_for=[{"activity": "Doorknocking"}, {"activity": "Phonebanking"}]
		)
		attempt.save()

		constituent = frappe.get_doc("OT Constituent", self.constituent.name)
		activities = sorted(r.activity for r in constituent.volunteers_for)

		self.assertEqual(activities, ["Doorknocking", "Phonebanking"])

	def test_nothing_escalates_without_a_constituent(self):
		"""No person means nothing to attach a signature or RSVP to."""
		before = frappe.db.count("OT Petition Signature")
		self._attempt(constituent=None, outcome="No answer", petition_signed=self.petition.name)

		self.assertEqual(frappe.db.count("OT Petition Signature"), before)


class TestCanvassPermissions(FrappeTestCase):
	"""The two-row if_owner pattern: volunteers see every knock on the block but can
	only correct their own. Verified against real users because the merge in
	get_role_permissions is subtle enough that reading the JSON is not proof."""

	VOLUNTEER = "canvasser-one@example.com"
	OTHER_VOLUNTEER = "canvasser-two@example.com"

	def setUp(self):
		for email in (self.VOLUNTEER, self.OTHER_VOLUNTEER):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": email.split("@")[0],
						"send_welcome_email": 0,
					}
				).insert(ignore_permissions=True)
				user.add_roles("OT Volunteer")

		self.address = frappe.get_doc(
			{
				"doctype": "OT Address",
				"address_line_1": "910 Perm Test St",
				"city": "Philadelphia",
				"state": "PA",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_volunteer_can_log_a_visit(self):
		frappe.set_user(self.VOLUNTEER)

		self.assertTrue(frappe.has_permission("OT Canvass Attempt", "create"))
		attempt = frappe.get_doc(
			{
				"doctype": "OT Canvass Attempt",
				"address": self.address.name,
				"outcome": "Answered",
			}
		).insert()

		self.assertEqual(attempt.owner, self.VOLUNTEER)

	def test_volunteer_can_edit_own_but_not_another_volunteers_visit(self):
		frappe.set_user(self.VOLUNTEER)
		mine = frappe.get_doc(
			{"doctype": "OT Canvass Attempt", "address": self.address.name, "outcome": "No answer"}
		).insert()

		frappe.set_user(self.OTHER_VOLUNTEER)
		theirs = frappe.get_doc(
			{"doctype": "OT Canvass Attempt", "address": self.address.name, "outcome": "Not interested"}
		).insert()

		self.assertTrue(frappe.has_permission("OT Canvass Attempt", "write", doc=theirs.name))
		self.assertFalse(
			frappe.has_permission("OT Canvass Attempt", "write", doc=mine.name),
			"a volunteer must not be able to rewrite another volunteer's field notes",
		)

	def test_volunteer_can_read_every_visit(self):
		"""Reads stay unscoped so canvassers can see a door was already knocked."""
		frappe.set_user(self.VOLUNTEER)
		mine = frappe.get_doc(
			{"doctype": "OT Canvass Attempt", "address": self.address.name, "outcome": "No answer"}
		).insert()

		frappe.set_user(self.OTHER_VOLUNTEER)

		self.assertTrue(frappe.has_permission("OT Canvass Attempt", "read", doc=mine.name))
		self.assertTrue(get_address_history(self.address.name))

	def test_volunteer_cannot_delete_visits(self):
		frappe.set_user(self.VOLUNTEER)

		self.assertFalse(frappe.has_permission("OT Canvass Attempt", "delete"))

	def test_volunteer_can_create_a_constituent_met_at_a_door(self):
		frappe.set_user(self.VOLUNTEER)

		self.assertTrue(frappe.has_permission("OT Constituent", "create"))
