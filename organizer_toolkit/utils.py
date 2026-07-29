import frappe
from geopy.geocoders import Nominatim
from rapidfuzz import fuzz


# Nominatim's usage policy requires an identifying user agent and blocks generic ones.
# Override per-site with `nominatim_user_agent` in site_config.json.
DEFAULT_USER_AGENT = "organizer_toolkit (CREATE Lab; iglesiascrmtech@gmail.com)"


@frappe.whitelist()
def get_coordinates(address_string):
	# Initialize the geocoder
	geolocator = Nominatim(
		user_agent=frappe.conf.get("nominatim_user_agent") or DEFAULT_USER_AGENT,
		timeout=10,
	)

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
