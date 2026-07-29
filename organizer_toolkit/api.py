import json

import frappe
from frappe.desk.doctype.tag.tag import get_tagged_docs, remove_tag
from rapidfuzz import fuzz

from organizer_toolkit.address_utils import normalize_street

SIMILARITY_THRESHOLD = 75.0


def _street_without_house_number(address_line_1):
	"""'1816 N Bucknell St.' -> 'north bucknell street'.

	Dropping the house number is what lets a candidate search find the neighbours on a
	block, not just the exact door.
	"""
	tokens = normalize_street(address_line_1).split(" ")

	if len(tokens) > 1 and tokens[0].isdigit():
		return " ".join(tokens[1:])

	return " ".join(tokens)


@frappe.whitelist()
def compare_against_name_and_address(first_name, last_name, address=None):
	"""Find existing constituents who look like the one being entered.

	Takes an OT Address link rather than typed text: since addresses are deduplicated on
	a normalized key, "same address" is now an exact match instead of a fuzzy one, and
	only the name needs fuzzy comparison.

	Candidates are narrowed to the same street before scoring. The previous version
	loaded every constituent and scored all of them, which is fine at a few hundred rows
	and quadratic misery at a few thousand.
	"""
	if not address:
		return []

	target = frappe.db.get_value("OT Address", address, ["address_line_1"], as_dict=True)

	if not target:
		return []

	street = _street_without_house_number(target.address_line_1)

	if not street:
		return []

	# Addresses on the same street, then the constituents living at them.
	nearby = frappe.get_all(
		"OT Address",
		filters={"address_key": ["like", f"%{street}%"]},
		fields=["name", "address_line_1"],
	)

	if not nearby:
		return []

	streets_by_address = {a.name: a.address_line_1 for a in nearby}

	candidates = frappe.get_list(
		"OT Constituent",
		filters={"address": ["in", list(streets_by_address)]},
		fields=["name", "first_name", "last_name", "address"],
		limit_page_length=0,
	)

	left = f"{first_name or ''} {last_name or ''} {target.address_line_1}"
	matches = []

	for candidate in candidates:
		candidate_street = streets_by_address.get(candidate.address, "")
		right = f"{candidate.first_name or ''} {candidate.last_name or ''} {candidate_street}"

		if fuzz.ratio(left, right) > SIMILARITY_THRESHOLD:
			# The client dialog labels each row with this, so keep the street on the row.
			candidate.street_address = candidate_street
			matches.append(candidate)

	return matches


@frappe.whitelist(allow_guest=False)
def fetch_ot_constituents(doctype, txt, searchfield, start, page_len, filters):
	frappe.only_for("System Manager")

	constituents = frappe.get_all("OT Constituent", filters=filters, fields=["*"])

	frappe.response["message"] = constituents


@frappe.whitelist()
def get_tags_for_docs(doctype, doc_names):

	if isinstance(doc_names, str):
		doc_names = json.loads(doc_names)

	tags = frappe.db.get_all(
		"Tag Link",
		filters={
			"document_type": doctype,
			"document_name": ["in", doc_names],
		},
		fields=["tag"],
		distinct=True,
	)

	return sorted([t.tag for t in tags])


@frappe.whitelist()
def remove_tags_from_docs(tags, doctype, doc_names):

	if isinstance(tags, str):
		tags = json.loads(tags)
	if isinstance(doc_names, str):
		doc_names = json.loads(doc_names)

	for tag in tags:
		for name in doc_names:
			remove_tag(tag=tag, dt=doctype, dn=name)

	frappe.db.commit()
	return {"removed": tags}


@frappe.whitelist()
def add_event_rsvp(constituent, event_name):
	doc = frappe.get_doc("OT Constituent", constituent)
	rsvp = doc.append("event_rsvps")
	rsvp.event = event_name

	doc.save()
