import json

import frappe
from frappe.desk.doctype.tag.tag import get_tagged_docs, remove_tag

# @frappe.whitelist()
# def remove_tags_from_doctype(tags, doctype="OT Constituent"):
# 	if isinstance(tags, str):
# 		tags = json.loads(tags)

# 	for tag in tags:
# 		# Get all docs with this tag using Frappe's own method
# 		affected = get_tagged_docs(doctype, f"%{tag}%")

# 		# Remove the tag from each doc using Frappe's own method
# 		for (doc_name,) in affected:
# 			remove_tag(tag=tag, dt=doctype, dn=doc_name)

# 	frappe.db.commit()
# 	return {"removed": tags}


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
