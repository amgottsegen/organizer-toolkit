import json

import frappe
from frappe.desk.doctype.tag.tag import get_tagged_docs, remove_tag
from rapidfuzz import fuzz


@frappe.whitelist()
def compare_against_name_and_address(first_name, last_name, street_address):
	if street_address is None or street_address.strip() == "":
		return []

	constituents = frappe.get_all(
		"OT Constituent", fields=["name", "first_name", "last_name", "street_address"]
	)
	left = f"{first_name} {last_name} {street_address}"
	similar_constituents = []

	for constituent in constituents:
		right = f"{constituent.first_name} {constituent.last_name} {constituent.street_address}"
		similarity = fuzz.ratio(left, right)

		if similarity > 75.0:
			similar_constituents.append(constituent)

	return similar_constituents


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
