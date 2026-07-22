"""
Regenerates the doorknocking Leaflet/folium map, pulling the Members layer
live from the OT Constituent doctype (filtered to type == "Member") and
keeping all other layers as static bundled files.
"""

import json
import os

import folium
import frappe
import pandas as pd
from folium.plugins import BeautifyIcon, HeatMap, Search

APP_NAME = "organizer_toolkit"
DEFAULT_CENTER = [39.986707, -75.141287]
MAP_FILENAME = "doorknocking_map.html"


def _data_path(*parts):
	"""Path to bundled static data shipped inside the app itself."""
	return frappe.get_app_path(APP_NAME, "doorknocking_data", *parts)


def _build_base_map():
	# token = frappe.conf.get("mapbox_token")

	m = folium.Map(location=DEFAULT_CENTER, zoom_start=15, tiles="CartoDB Voyager")

	# if token:
	#     folium.TileLayer(
	#         tiles=(
	#             "https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v11/"
	#             f"tiles/512/{{z}}/{{x}}/{{y}}@2x?access_token={token}"
	#         ),
	#         attr="Mapbox",
	#         name="Mapbox Satellite",
	#         overlay=False,
	#         control=True,
	#         show=False,
	#     ).add_to(m)

	return m


def _add_static_layers(m):
	lots_path = frappe.get_site_path("private", "files", "target_lots.csv")
	stewards_path = frappe.get_site_path("private", "files", "target_stewards.csv")
	zones_geojson_path = frappe.get_site_path("private", "files", "zones_v2.geojson")
	district_geojson_path = frappe.get_app_path(
		"organizer_toolkit", "public", "geojson", "Council_Districts_2024.geojson"
	)

	if os.path.exists(zones_geojson_path):
		folium.GeoJson(
			zones_geojson_path,
			name="Doorknocking Zones",
			highlight_function=lambda x: {"weight": 3, "color": "red"},
			color="yellow",
			dash_array="5, 5",
			zoom_on_click=True,
			popup=folium.GeoJsonPopup(fields=["Name"], labels=False, localize=True),
		).add_to(m)

	if os.path.exists(district_geojson_path):
		folium.GeoJson(
			district_geojson_path,
			name="Council Districts",
			highlight_function=lambda x: {"weight": 3, "color": "white"},
			color="black",
			popup=folium.GeoJsonPopup(fields=["DISTRICT"], labels=False, localize=True),
			show=False,
		).add_to(m)

	if os.path.exists(lots_path) and os.path.exists(stewards_path):
		lots_cream = pd.read_csv(lots_path)
		cream = pd.read_csv(stewards_path)

		for _, row in lots_cream.iterrows():
			popup_content = f"""
			<div>
				<p><b>Address:</b> {row.location}</p>
				<p><b>Owner:</b> {row.owner_1}</p>
				<p><b>Market Value:</b> ${row.market_value}</p>
				<b>Other Resources:</b><br>
				<a class="btn btn-light" role="button"
				href="https://atlas.phila.gov/{row.location}/property" target="_blank">Atlas</a>
				<a class="btn btn-light" role="button"
				href="https://www.google.com/maps/search/{row.location}" target="_blank">Google Maps</a>
				<br><br>
				<a class="btn btn-outline-success btn-lg" role="button"
				href="https://jotform.com/251974322359059?lotAddress={row.location}"
				target="_blank">Enter survey notes</a><br><br>
			</div>
			"""
			folium.CircleMarker(
				location=[row.lat, row.lng],
				popup=folium.Popup(popup_content, max_width=300),
				color="black",
				weight=0.3,
				fill=True,
				fill_color="green",
				fill_opacity=0.5,
				radius=4,
				tags=["Lots"],
			).add_to(m)

		for _, row in cream.drop_duplicates(subset=["location"]).iterrows():
			popup_content = f"""
			<div>
				<p><b>Address:</b> {row.location}</p>
				<p><b>Owner:</b> {row.owner_1}</p>
				<p><b>Market Value:</b> ${row.market_value}</p>
				<p><b>Lot Address:</b> {row.lot_address}</p>
				<p><b>Lot Owner:</b> {row.lot_owner}</p>
				<b>Other Resources:</b><br>
				<a class="btn btn-light" role="button"
				href="https://atlas.phila.gov/{row.location}/property" target="_blank">Atlas</a>
				<a class="btn btn-light" role="button"
				href="https://www.google.com/maps/search/{row.location}" target="_blank">Google Maps</a>
				<br><br>
				<a class="btn btn-outline-success btn-lg" role="button"
				href="https://jotform.com/251974322359059?lotAddress={row.location}"
				target="_blank">Enter survey notes</a><br><br>
			</div>
			"""
			folium.CircleMarker(
				location=[row.lat, row.lng],
				popup=folium.Popup(popup_content, max_width=300),
				color="black",
				weight=0.3,
				fill=True,
				fill_color="lightpink",
				fill_opacity=0.7,
				radius=4,
				tags=["Houses"],
			).add_to(m)

		heat_data = [[row.lat, row.lng] for _, row in cream.iterrows()]
		HeatMap(heat_data, name="Heat Map").add_to(m)


def _extract_lat_lon(location_value):
	"""Safely pull (lat, lon) out of a Frappe Geolocation field.

	The field is stored as a GeoJSON FeatureCollection string, e.g.:
	    {"type": "FeatureCollection", "features": [
	        {"type": "Feature", "geometry": {"type": "Point",
	         "coordinates": [-75.1460133, 39.9902584]}, "properties": {}}
	    ]}

	Note GeoJSON orders coordinates as [longitude, latitude] -- the
	reverse of what folium wants. Returns None if the field is empty,
	malformed, or has no usable point so callers can just skip the row.
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
			title="Doorknocking map: bad location value",
			message=f"Could not parse location field: {location_value!r}",
		)
		return None


def _add_members_layer(m):
	# Adjust fieldnames to match your OT Constituent doctype.
	members = frappe.get_all(
		"OT Constituent",
		filters={"type": "Member"},
		fields=["name", "full_name", "street_address", "location"],
	)

	member_layer = folium.FeatureGroup(name="Members", show=False)

	for row in members:
		coords = _extract_lat_lon(row.get("location"))
		if coords is None:
			continue
		lat, lon = coords

		name = frappe.utils.escape_html(row.get("full_name") or "")
		address = frappe.utils.escape_html(row.get("street_address") or "")

		popup_content = f"""
        <div>
            <p><b>Member:</b> {name}</p>
            <p><b>Address:</b> {address}</p>
            <a class="btn btn-outline-success btn-lg" role="button"
               href="/app/ot-constituent/{row["name"]}">View Constituent Details</a><br><br>
        </div>
        """

		folium.Marker(
			location=[lat, lon],
			popup=folium.Popup(popup_content, max_width=300),
			icon=BeautifyIcon(
				icon="star",
				inner_icon_style="color:#0C0096;font-size:14px;",
				background_color="transparent",
				border_color="transparent",
			),
			name=name,
		).add_to(member_layer)

	member_layer.add_to(m)

	Search(
		layer=member_layer,
		search_label="name",
		placeholder="Search members by name",
		collapsed=False,
	).add_to(m)


@frappe.whitelist()
def generate_doorknocking_map():
	"""Rebuild the map HTML and save it into the site's public files.

	Returns the URL the frontend can point an <iframe> or link at.
	"""
	m = _build_base_map()
	_add_static_layers(m)
	_add_members_layer(m)
	folium.LayerControl().add_to(m)

	out_path = frappe.get_site_path("public", "files", MAP_FILENAME)
	os.makedirs(os.path.dirname(out_path), exist_ok=True)
	m.save(out_path)

	return {"url": f"/files/{MAP_FILENAME}"}


def regenerate_on_constituent_change(doc, method=None):
	"""doc_events hook: queue a regeneration whenever a Member changes.

	Wire this up in hooks.py (see below) on OT Constituent's
	after_insert / on_update / on_trash. Queued rather than run inline so
	a bulk import doesn't rebuild the map hundreds of times in a row.
	"""
	if doc.get("type") != "Member":
		return

	frappe.enqueue(
		"organizer_toolkit.doorknocking.doorknocking_map.generate_doorknocking_map",
		queue="short",
		job_name="regenerate_doorknocking_map",
		deduplicate=True,  # skip if one's already queued
	)
