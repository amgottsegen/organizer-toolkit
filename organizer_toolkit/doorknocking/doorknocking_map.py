"""
Regenerates the doorknocking Leaflet/folium map, pulling the Members layer
live from the OT Constituent doctype (filtered to type == "Member") and
keeping all other layers as static bundled files.
"""

import os

import folium
import frappe
import pandas as pd
from folium.plugins import BeautifyIcon, HeatMap, Search

from organizer_toolkit.locality import (
	get_district_boundaries_path,
	get_locality,
	get_parcel_lookup_url,
)

APP_NAME = "organizer_toolkit"
MAP_FILENAME = "doorknocking_map.html"


def _data_path(*parts):
	"""Path to bundled static data shipped inside the app itself."""
	return frappe.get_app_path(APP_NAME, "doorknocking_data", *parts)


def _map_center():
	locality = get_locality()

	return [locality["map_center_latitude"], locality["map_center_longitude"]]


def _parcel_link(address):
	"""Anchor to the city's property-record system, or empty if none is configured."""
	url = get_parcel_lookup_url(address)

	if not url:
		return ""

	return f'<a class="btn btn-light" role="button" href="{url}" target="_blank">Property Records</a>'


def _log_visit_url(address_line_1):
	"""Deep link into the canvass form with the street prefilled.

	Replaces the JotForm hand-off this map used to send canvassers to -- visits now land
	in OT Canvass Attempt instead of a second system nobody could report on.
	"""
	from urllib.parse import urlencode

	query = urlencode({"address_line_1": address_line_1 or ""})

	return f"/app/ot-canvass-attempt/new?{query}"


def _build_base_map():
	# token = frappe.conf.get("mapbox_token")

	m = folium.Map(location=_map_center(), zoom_start=15, tiles="CartoDB Voyager")

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
	district_geojson_path = get_district_boundaries_path()

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
			name=f"{get_locality('district_label')}s",
			highlight_function=lambda x: {"weight": 3, "color": "white"},
			color="black",
			popup=folium.GeoJsonPopup(
				fields=[get_locality("district_property_key")], labels=False, localize=True
			),
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
				{_parcel_link(row.location)}
				<a class="btn btn-light" role="button"
				href="https://www.google.com/maps/search/{row.location}" target="_blank">Google Maps</a>
				<br><br>
				<a class="btn btn-outline-success btn-lg" role="button"
				href="{_log_visit_url(row.location)}">Log a visit</a><br><br>
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
				{_parcel_link(row.location)}
				<a class="btn btn-light" role="button"
				href="https://www.google.com/maps/search/{row.location}" target="_blank">Google Maps</a>
				<br><br>
				<a class="btn btn-outline-success btn-lg" role="button"
				href="{_log_visit_url(row.location)}">Log a visit</a><br><br>
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


def _add_members_layer(m):
	members = frappe.get_all(
		"OT Constituent",
		filters={"type": "Member", "address": ["is", "set"]},
		fields=["name", "full_name", "address"],
	)

	if not members:
		return

	# Coordinates now live on OT Address as flat columns, so there is no GeoJSON to
	# parse here any more. Ungeocoded addresses store 0/0 rather than NULL (Frappe Float
	# columns are NOT NULL), so filter that sentinel out -- 0,0 is in the Gulf of Guinea
	# and would otherwise plot as a real pin.
	addresses = {
		a.name: a
		for a in frappe.get_all(
			"OT Address",
			filters={"name": ["in", [m.address for m in members]], "latitude": ["!=", 0]},
			fields=["name", "address_line_1", "latitude", "longitude"],
		)
	}

	member_layer = folium.FeatureGroup(name="Members", show=False)

	for row in members:
		location = addresses.get(row.address)
		if location is None:
			continue

		lat, lon = location.latitude, location.longitude

		name = frappe.utils.escape_html(row.get("full_name") or "")
		address = frappe.utils.escape_html(location.address_line_1 or "")

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
		# deduplicate keys off job_id; passing job_name raises "job_id parameter is
		# required for deduplication". Latent until the doc_events hook is enabled.
		job_id="regenerate_doorknocking_map",
		deduplicate=True,  # skip if one's already queued
	)
