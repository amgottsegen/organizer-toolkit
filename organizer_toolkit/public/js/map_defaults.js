// Make sure we have a dictionary to add our custom settings
const map_settings = frappe.provide("frappe.utils.map_defaults");

// New default location & zoom
map_settings.center = [ 39.9526, -75.1652];
map_settings.zoom = 12;

// Use a different map: satellite instead of streets
// Examples can be found at https://leaflet-extras.github.io/leaflet-providers/preview/
map_settings.tiles = "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
map_settings.attribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'