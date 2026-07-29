// Make sure we have a dictionary to add our custom settings
const map_settings = frappe.provide("frappe.utils.map_defaults");

// Default location & zoom come from OT Locality Settings, published into the boot
// payload by organizer_toolkit.boot.boot_session. This file is a static asset loaded
// before any form, so it cannot query the server -- the literals below are only a
// fallback for when boot has not been populated yet.
const ot_locality = (window.frappe && frappe.boot && frappe.boot.ot_locality) || {};

map_settings.center = [
    ot_locality.map_center_latitude || 39.9526,
    ot_locality.map_center_longitude || -75.1652,
];
map_settings.zoom = ot_locality.map_default_zoom || 12;

// Use a different map: satellite instead of streets
// Examples can be found at https://leaflet-extras.github.io/leaflet-providers/preview/
map_settings.tiles = "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
map_settings.attribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
