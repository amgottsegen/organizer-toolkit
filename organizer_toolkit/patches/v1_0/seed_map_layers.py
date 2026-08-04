"""Seed the map layers an organizer would otherwise have to build by hand.

These four mirror what `doorknocking/doorknocking_map.py` hardcodes in folium, so the
first thing anyone sees when they open a map is the same set of pins they are used to.

Seeded by patch rather than shipped as a fixture: a fixture would re-import on every
migrate and quietly undo any restyling or refiltering done in the desk. Colours and
filters are meant to be changed.

Idempotent: a layer that already exists is left alone.
"""

import os

import frappe

TARGET_LOTS_FILE = ("private", "files", "target_lots.csv")

LAYERS = [
	{
		"layer_name": "Addresses",
		"display_order": 40,
		"description": "Every geocoded address on file. The layer to cut turf around.",
		"source_type": "DocType",
		"source_doctype": "OT Address",
		"label_field": "address_line_1",
		"color": "#8D8D8D",
		"marker_shape": "Circle",
		"marker_size": 4,
		"fill_opacity": 0.5,
		"line_weight": 0,
		"max_features": 5000,
	},
	{
		"layer_name": "Doors Knocked",
		"display_order": 20,
		"description": "Every canvass attempt, wherever its address was geocoded.",
		"source_type": "DocType",
		"source_doctype": "OT Canvass Attempt",
		"color": "#28A745",
		"marker_shape": "Circle",
		"marker_size": 5,
		"fill_opacity": 0.7,
		"line_weight": 0,
	},
	{
		"layer_name": "Canvass Zones",
		"display_order": 50,
		"description": "Existing zone boundaries — check a new zone against these before drawing.",
		"source_type": "DocType",
		"source_doctype": "OT Canvass Zone",
		"label_field": "zone_name",
		"filters_json": '[["OT Canvass Zone","is_active","=","1"]]',
		"color": "#FFC107",
		"marker_shape": "Circle",
		"marker_size": 6,
		# Nearly see-through: these are drawn on top of the pins being cut into turf.
		"fill_opacity": 0.1,
		"line_weight": 2,
	},
	{
		"layer_name": "Doorknocking Volunteers",
		"display_order": 10,
		"description": "People who said they would help knock doors. Filtered on a child "
		"table, which is why the layer resolves names before asking for coordinates.",
		"source_type": "DocType",
		"source_doctype": "OT Constituent",
		"label_field": "full_name",
		"filters_json": '[["OT Activity Child","activity","=","Doorknocking"]]',
		"color": "#D63384",
		"marker_shape": "Pin",
		"marker_size": 7,
		"fill_opacity": 0.9,
		"line_weight": 1,
	},
	{
		"layer_name": "Target Lots",
		"display_order": 30,
		"description": "The static lot list. Becomes a doctype layer once the Lots app lands.",
		"source_type": "File",
		"source_file": "/" + "/".join(TARGET_LOTS_FILE),
		"color": "#1E7E34",
		"marker_shape": "Square",
		"marker_size": 4,
		"fill_opacity": 0.6,
		"line_weight": 0,
		"max_features": 3000,
	},
]


def execute():
	if not frappe.db.table_exists("OT Map Layer"):
		return

	created = skipped = ordered = 0

	for layer in LAYERS:
		if frappe.db.exists("OT Map Layer", layer["layer_name"]):
			skipped += 1

			# Layers seeded before display_order existed sit at 0, which stacks them
			# alphabetically. Only fill in the intended order where nobody has set one --
			# a value someone chose is not ours to overwrite.
			if not frappe.db.get_value("OT Map Layer", layer["layer_name"], "display_order"):
				frappe.db.set_value(
					"OT Map Layer", layer["layer_name"], "display_order", layer["display_order"]
				)
				ordered += 1

			continue

		if layer["source_type"] == "DocType" and not frappe.db.table_exists(layer["source_doctype"]):
			continue

		# A layer pointing at a file that is not there throws the moment it is ticked on,
		# and the file is site data rather than something the app ships.
		if layer["source_type"] == "File" and not os.path.exists(frappe.get_site_path(*TARGET_LOTS_FILE)):
			print(f"  skipping {layer['layer_name']}: {layer['source_file']} is not on this site")
			continue

		frappe.get_doc({"doctype": "OT Map Layer", "enabled": 1, **layer}).insert(
			ignore_permissions=True
		)
		created += 1

	frappe.db.commit()

	print(f"  seeded {created} map layer(s); {skipped} already present, {ordered} restacked")
