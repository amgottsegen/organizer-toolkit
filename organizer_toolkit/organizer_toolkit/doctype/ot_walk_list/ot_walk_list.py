# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

from organizer_toolkit.organizer_toolkit.doctype.ot_canvass_zone.ot_canvass_zone import (
	addresses_within,
)


class OTWalkList(Document):
	def validate(self):
		self.drop_duplicate_addresses()

	def on_update(self):
		self.propagate_zone()

	def propagate_zone(self):
		"""Carry this list's zone onto the doors already knocked from it.

		`fetch_from` copies once, at save time, so doors worked before the zone was filled
		in would stay unlabelled forever. This is the only thing that moves a doorknock's
		zone -- redrawing a boundary deliberately does not, so the label stays the zone
		the door was actually canvassed for.
		"""
		if not self.has_value_changed("zone"):
			return

		frappe.db.set_value(
			"OT Canvass Attempt",
			{"walk_list": self.name},
			"zone",
			self.zone,
			update_modified=False,
		)

	def drop_duplicate_addresses(self):
		"""One row per door.

		Populating from a zone twice, or adding a door by hand that the zone already
		pulled in, would otherwise leave a canvasser knocking the same house twice.
		"""
		seen = set()
		unique_rows = []

		for row in self.addresses:
			if not row.address or row.address in seen:
				continue

			seen.add(row.address)
			unique_rows.append(row)

		if len(unique_rows) != len(self.addresses):
			self.addresses = unique_rows
			for index, row in enumerate(self.addresses, start=1):
				row.idx = index


@frappe.whitelist()
def populate_from_zone(walk_list, zone=None):
	"""Add every geocoded address inside the zone boundary to this walk list.

	Additive rather than replacing: an organizer may have already added doors by hand,
	and `validate` drops duplicates, so running this twice is harmless.
	"""
	doc = frappe.get_doc("OT Walk List", walk_list)
	zone = zone or doc.zone

	if not zone:
		frappe.throw(_("Pick a zone first."))

	existing = {row.address for row in doc.addresses}
	added = 0

	for address in addresses_within(zone):
		if address in existing:
			continue

		doc.append("addresses", {"address": address})
		added += 1

	if added:
		doc.save()

	return {"added": added, "total": len(doc.addresses)}


@frappe.whitelist()
def create_from_addresses(addresses, list_name, canvass_date=None, assigned_to=None, zone=None):
	"""Build a walk list out of an explicit selection of doors.

	The zone path covers "everything inside this boundary"; this covers everything else --
	a handful of streets, the doors nobody answered last week, a filtered list. Ungeocoded
	addresses are kept: unlike zone population, the selection says which doors are meant,
	so coordinates are not needed to decide.

	The zone is optional but worth setting: it becomes the label on every doorknock logged
	from this list, and it is the only record of which turf the work belonged to.
	"""
	addresses = frappe.parse_json(addresses) or []

	if not addresses:
		frappe.throw(_("Select at least one address."))

	doc = frappe.new_doc("OT Walk List")
	doc.list_name = list_name
	doc.canvass_date = canvass_date or nowdate()
	doc.assigned_to = assigned_to
	doc.zone = zone

	for address in addresses:
		doc.append("addresses", {"address": address})

	# validate() collapses any repeats, so the count comes from the saved rows.
	doc.insert()

	return {"name": doc.name, "total": len(doc.addresses)}


@frappe.whitelist()
def get_progress(walk_list):
	"""How much of this list has been knocked.

	Derived from canvass attempts rather than stored on the rows: a status field would
	need keeping in sync with every visit, and would drift the moment someone logged a
	door outside the walk list flow.
	"""
	doc = frappe.get_cached_doc("OT Walk List", walk_list)
	addresses = [row.address for row in doc.addresses if row.address]

	if not addresses:
		return {"total": 0, "knocked": 0, "remaining": []}

	knocked = set(
		frappe.get_all(
			"OT Canvass Attempt",
			filters={"walk_list": walk_list, "address": ["in", addresses]},
			pluck="address",
			limit_page_length=0,
		)
	)

	return {
		"total": len(addresses),
		"knocked": len(knocked),
		"remaining": [a for a in addresses if a not in knocked],
	}
