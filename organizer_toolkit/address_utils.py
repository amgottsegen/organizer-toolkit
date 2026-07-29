"""Address normalization shared by the OT Address controller and the migration patches.

The point of `build_address_key` is deduplication. Two canvassers standing at the same
door will type "1423 S 52nd St" and "1423 South 52nd Street"; the City of Philadelphia's
parcel records say "1423 S 52ND ST". All three must collapse to one key so they land on
one OT Address record instead of three, splitting that door's canvass history.

Consistency matters more than linguistic correctness here -- the key is never displayed,
it only has to be stable for the same physical address.
"""

import json
import re

import frappe

# Expanded only when the token appears in street-type position (last, or second-to-last
# when a trailing directional is present). Deliberately NOT applied elsewhere, so
# "100 St James Pl" keeps "St" as-is rather than becoming "street james place".
STREET_TYPES = {
	"st": "street",
	"str": "street",
	"ave": "avenue",
	"av": "avenue",
	"rd": "road",
	"blvd": "boulevard",
	"dr": "drive",
	"ln": "lane",
	"ct": "court",
	"pl": "place",
	"ter": "terrace",
	"terr": "terrace",
	"pkwy": "parkway",
	"pky": "parkway",
	"cir": "circle",
	"sq": "square",
	"hwy": "highway",
	"aly": "alley",
	"walk": "walk",
	"way": "way",
	"row": "row",
}

DIRECTIONALS = {
	"n": "north",
	"s": "south",
	"e": "east",
	"w": "west",
	"ne": "northeast",
	"nw": "northwest",
	"se": "southeast",
	"sw": "southwest",
}

# Unit designators in address_line_2 -- "Apt 2", "# 2", "Unit 2" are the same unit.
UNIT_DESIGNATORS = {"apt", "apartment", "unit", "ste", "suite", "fl", "floor", "rm", "room", "#"}

_PUNCTUATION = re.compile(r"[.,;:'\"()]")
_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _tokenize(value):
	"""Lowercase, strip punctuation, collapse whitespace, split."""
	if not value:
		return []

	value = _PUNCTUATION.sub(" ", str(value).lower())
	value = value.replace("-", " ")
	value = _WHITESPACE.sub(" ", value).strip()

	return value.split(" ") if value else []


def normalize_street(line):
	"""Normalize a street line: '1423 S 52nd St.' -> '1423 south 52nd street'."""
	tokens = _tokenize(line)
	if not tokens:
		return ""

	# A trailing directional ("Main St NW") sits after the street type, so resolve it
	# first and let the street type be found in the position it vacates.
	trailing_directional = None
	if len(tokens) > 2 and tokens[-1] in DIRECTIONALS:
		trailing_directional = DIRECTIONALS[tokens[-1]]
		tokens = tokens[:-1]

	if len(tokens) > 1 and tokens[-1] in STREET_TYPES:
		tokens[-1] = STREET_TYPES[tokens[-1]]

	# Leading/interior directionals ("1423 S 52nd"), never the first or last token --
	# the first is the house number and the last is the street type or name.
	for i in range(1, len(tokens) - 1):
		if tokens[i] in DIRECTIONALS:
			tokens[i] = DIRECTIONALS[tokens[i]]

	if trailing_directional:
		tokens.append(trailing_directional)

	return " ".join(tokens)


def normalize_unit(line):
	"""Normalize a unit line: 'Apt. 2B' / '# 2b' / 'Unit 2B' -> '2b'."""
	tokens = _tokenize(line)
	tokens = [t for t in tokens if t not in UNIT_DESIGNATORS]

	# "#2b" arrives as a single token once punctuation is stripped to a space, but a
	# bare "#" glued to the number survives -- drop any leftover non-alphanumerics.
	tokens = [_NON_ALNUM.sub("", t) for t in tokens]

	return " ".join(t for t in tokens if t)


def normalize_postal_code(value):
	"""Keep the 5-digit base only -- ZIP+4 is inconsistently recorded."""
	if not value:
		return ""

	digits = re.sub(r"[^0-9]", "", str(value))

	return digits[:5]


def build_address_key(address_line_1, address_line_2=None, city=None):
	"""Build the unique dedupe key for an OT Address.

	Deliberately excludes the postal code. Within one municipality a street plus house
	number *is* the door -- the ZIP is a property of that door, not part of its
	identity. Including it made the key brittle in exactly the situation it exists for:
	a canvasser at the door rarely knows the ZIP, so the same address entered with and
	without one produced two records and split that door's history. (6069 Reinhard St
	was already duplicated this way before the key was changed.)

	Returns an empty string when there is no street line at all, which the caller is
	expected to reject -- an address with no street cannot be deduplicated.
	"""
	street = normalize_street(address_line_1)
	if not street:
		return ""

	return "|".join(
		[
			street,
			normalize_unit(address_line_2),
			" ".join(_tokenize(city)),
		]
	)


def extract_lat_lon(location_value):
	"""Safely pull (lat, lon) out of a Frappe Geolocation field.

	The field is stored as a GeoJSON FeatureCollection string, e.g.:
	    {"type": "FeatureCollection", "features": [
	        {"type": "Feature", "geometry": {"type": "Point",
	         "coordinates": [-75.1460133, 39.9902584]}, "properties": {}}
	    ]}

	Note GeoJSON orders coordinates as [longitude, latitude] -- the reverse of what
	folium and Leaflet want. Returns None if the field is empty, malformed, or has no
	usable point so callers can just skip the row.
	"""
	if not location_value:
		return None

	try:
		data = json.loads(location_value) if isinstance(location_value, str) else location_value
		features = data.get("features") or []
		if not features:
			return None

		geometry = features[0].get("geometry") or {}
		if geometry.get("type") != "Point":
			return None

		coords = geometry.get("coordinates") or []
		if len(coords) != 2:
			return None

		lon, lat = coords
		return float(lat), float(lon)
	except (ValueError, TypeError, AttributeError, KeyError):
		frappe.log_error(
			title="Address: bad location value",
			message=f"Could not parse location field: {location_value!r}",
		)
		return None


def build_location_geojson(lat, lon):
	"""Inverse of `extract_lat_lon` -- build the FeatureCollection a Geolocation stores."""
	return frappe.as_json(
		{
			"type": "FeatureCollection",
			"features": [
				{
					"type": "Feature",
					"geometry": {"type": "Point", "coordinates": [lon, lat]},
					"properties": {},
				}
			],
		}
	)
