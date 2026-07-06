import frappe
from geopy.geocoders import Nominatim
from rapidfuzz import fuzz


@frappe.whitelist()
def get_coordinates(address_string):
	# Initialize the geocoder
	geolocator = Nominatim(user_agent="frappe_app")

	try:
		location = geolocator.geocode(address_string)
		if location:
			return {
				"latitude": location.latitude,
				"longitude": location.longitude,
				"address": location.address,
			}
		else:
			frappe.throw(f"Location {address_string} not found")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Geopy Geocoding Error")
		return None
