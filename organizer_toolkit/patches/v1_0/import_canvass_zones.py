"""Import doorknocking zones from the site's zones_v2.geojson into OT Canvass Zone.

The zones lived as a file in `private/files`, which meant they could only be changed by
replacing the file and they could not be linked to anything. As records they can be
drawn on a map, filtered by day, and used to populate a walk list.

The source file encodes the day in the feature name -- "Zone 1: Monday" -- and the
neighbourhood in `description`, so both fields come across without a manual mapping.

Idempotent: zones already present are left alone, so a re-run cannot overwrite a
boundary an organizer has since redrawn.
"""

import json
import os
import re

import frappe

SOURCE_FILE = ("private", "files", "zones_v2.geojson")

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def execute():
	if not frappe.db.table_exists("OT Canvass Zone"):
		return

	path = frappe.get_site_path(*SOURCE_FILE)

	if not os.path.exists(path):
		print(f"  no zones file at {os.path.join(*SOURCE_FILE)}; nothing to import")
		return

	with open(path) as f:
		data = json.load(f)

	created = skipped = 0

	for feature in data.get("features") or []:
		properties = feature.get("properties") or {}
		raw_name = (properties.get("Name") or "").strip()

		if not raw_name or not feature.get("geometry"):
			continue

		zone_name, day = _split_name_and_day(raw_name)

		if frappe.db.exists("OT Canvass Zone", zone_name):
			skipped += 1
			continue

		frappe.get_doc(
			{
				"doctype": "OT Canvass Zone",
				"zone_name": zone_name,
				"neighbourhood": (properties.get("description") or "").strip() or None,
				"day_of_week": day,
				"is_active": 1,
				# Wrap the bare geometry back into the FeatureCollection a Geolocation
				# field expects, so the boundary is drawable in the form.
				"location": frappe.as_json(
					{
						"type": "FeatureCollection",
						"features": [
							{
								"type": "Feature",
								"geometry": feature["geometry"],
								"properties": {},
							}
						],
					}
				),
			}
		).insert(ignore_permissions=True)
		created += 1

	frappe.db.commit()

	print(f"  imported {created} canvass zone(s); {skipped} already present")


def _split_name_and_day(raw_name):
	"""'Zone 1: Monday' -> ('Zone 1', 'Monday'). Falls back to the whole string."""
	match = re.match(r"^(.*?)\s*:\s*(\w+)\s*$", raw_name)

	if match and match.group(2).capitalize() in DAYS:
		return match.group(1).strip(), match.group(2).capitalize()

	return raw_name, None
