# Copyright (c) 2026, CREATE Lab and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from organizer_toolkit.address_utils import (
	build_address_key,
	build_location_geojson,
	extract_lat_lon,
)
from organizer_toolkit.locality import find_district
from organizer_toolkit.utils import get_coordinates


class OTAddress(Document):
	def validate(self):
		self.address_key = build_address_key(self.address_line_1, self.address_line_2, self.city)

		if not self.address_key:
			frappe.throw(_("Street Address is required."))

		self.check_for_duplicate()

	def before_save(self):
		# Keep the flat columns in step with the Geolocation field so the map can filter
		# by bounding box without parsing GeoJSON for every row.
		#
		# Frappe Float columns are NOT NULL, so an ungeocoded address stores 0/0 rather
		# than NULL. Callers must exclude that sentinel -- 0,0 is a real coordinate in
		# the Gulf of Guinea and would otherwise plot as a legitimate pin.
		coords = extract_lat_lon(self.location)

		self.latitude, self.longitude = coords if coords else (0, 0)

		# District follows the coordinates whatever set them -- the geocoder, a device
		# GPS fix, or someone dragging the pin on the map widget. Deriving it here rather
		# than in each caller means no path can leave it stale.
		if not coords:
			self.municipal_district = None
		elif self.has_value_changed("location") or not self.municipal_district:
			self.municipal_district = find_district(*coords)

	def after_insert(self):
		self.queue_geocoding()

	def on_update(self):
		self.propagate_location_to_canvass_attempts()

	def queue_geocoding(self):
		"""Resolve coordinates in the background for addresses created away from a door.

		Backgrounded rather than inline because Nominatim's usage policy is one request
		per second -- geocoding on save would stall the canvasser and could get the
		organization blocked during a bulk import.
		"""
		if self.location:
			# A device GPS fix already landed; nothing to look up.
			return

		frappe.enqueue(
			"organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address.geocode_in_background",
			queue="long",
			# deduplicate keys off job_id, not job_name -- passing the latter raises.
			job_id=f"ot_geocode_{self.name}",
			deduplicate=True,
			# Hand the worker a row that definitely exists: without this the job can be
			# picked up before the transaction that created the address has committed.
			enqueue_after_commit=True,
			doc_name=self.name,
		)

	def propagate_location_to_canvass_attempts(self):
		"""Push new coordinates onto doorknocks already recorded at this address.

		`fetch_from` copies once, at save time. A visit logged before its address was
		geocoded would keep a blank location forever -- so the backfill would fix the
		addresses and the map would stay empty. This is what closes that gap.
		"""
		if not self.location or not self.has_value_changed("location"):
			return

		if not frappe.db.table_exists("OT Canvass Attempt"):
			return

		frappe.db.set_value(
			"OT Canvass Attempt",
			{"address": self.name},
			"location",
			self.location,
			update_modified=False,
		)

	def check_for_duplicate(self):
		"""Surface the unique constraint on address_key as a usable message.

		Without this the canvasser gets a raw MariaDB duplicate-key error and no way to
		reach the record they should have been editing.
		"""
		filters = {"address_key": self.address_key}
		if not self.is_new():
			filters["name"] = ("!=", self.name)

		existing = frappe.db.get_value("OT Address", filters, "name")

		if existing:
			frappe.throw(
				_("This address already exists as {0}.").format(
					f'<a href="/app/ot-address/{existing}">{existing}</a>'
				),
				title=_("Duplicate Address"),
			)


def find_or_create_address(
	address_line_1, address_line_2=None, city=None, state=None, postal_code=None, source="Manual Entry"
):
	"""Return the OT Address for these components, creating it only if new.

	Deduplication happens on the normalized address_key, so callers can pass whatever
	the user typed. Used by the migration patches and by field data entry.
	"""
	address_key = build_address_key(address_line_1, address_line_2, city)

	if not address_key:
		return None

	existing = frappe.db.get_value("OT Address", {"address_key": address_key}, "name")
	if existing:
		return frappe.get_doc("OT Address", existing)

	doc = frappe.get_doc(
		{
			"doctype": "OT Address",
			"address_line_1": address_line_1,
			"address_line_2": address_line_2,
			"city": city,
			"state": state,
			"postal_code": postal_code,
			"source": source,
		}
	)
	doc.insert()

	return doc


def set_coordinates(doc, lat, lon, save=True):
	"""Stamp a fix onto an address, whatever its source.

	Only the location is set here -- `before_save` derives the flat lat/lon columns and
	the district from it, so every path produces the same result.
	"""
	doc.location = build_location_geojson(lat, lon)

	if save:
		doc.save(ignore_permissions=True)

	return {"lat": lat, "lon": lon}


def geocode(doc, throw_on_failure=False):
	"""Resolve an address through Nominatim and store the result.

	Plain function rather than the whitelisted entry point so the button, the background
	queue and the backfill all share one path. Returns None when it could not resolve.
	"""
	if not doc.address_line_1 or not doc.city:
		message = _("Address {0} needs both a street address and a city before geocoding.").format(
			doc.name
		)
		if throw_on_failure:
			frappe.throw(message)
		return None

	address_string = ", ".join(filter(None, [doc.address_line_1, doc.city, doc.state]))
	result = get_coordinates(address_string)

	if result is None:
		frappe.log_error(
			title="Geocoding failed",
			message=f"Geocoding failed for address {doc.name}: {address_string}",
		)
		if throw_on_failure:
			frappe.throw(_("Geocoding failed. Please check the address and try again."))
		return None

	return set_coordinates(doc, result["latitude"], result["longitude"])


@frappe.whitelist()
def geocode_address(doc_name):
	"""Geocode on demand, from the form button or the list bulk action."""
	doc = frappe.get_doc("OT Address", doc_name)

	return geocode(doc, throw_on_failure=True)


@frappe.whitelist()
def set_device_location(doc_name, latitude, longitude):
	"""Record the canvasser's own GPS fix for a door they are standing at.

	More accurate than a geocoder's rooftop guess, instant, and not subject to
	Nominatim's rate limit -- so this is the preferred source during field entry.
	"""
	doc = frappe.get_doc("OT Address", doc_name)

	return set_coordinates(doc, flt(latitude), flt(longitude))


def geocode_in_background(doc_name):
	"""Queue target. Skips silently if the address gained coordinates in the meantime."""
	doc = frappe.get_doc("OT Address", doc_name)

	if doc.location:
		return

	geocode(doc)
