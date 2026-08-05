// Reference layers on every map in the desk.
//
// A canvasser cutting turf cannot draw a sensible zone over an empty basemap -- the whole
// job is drawing *around* pins that already exist. This puts a layer control on the
// Geolocation field and on list Map Views, backed by the OT Map Layer doctype.
//
// Layers are lazy: the control is built from a list of names and styles, and a layer's
// features are only fetched the first time somebody ticks it on.

frappe.provide("organizer_toolkit.map_layers");

(() => {
    const DEFAULTS = { color: "#2490EF", marker_size: 6, fill_opacity: 0.6, line_weight: 1 };

    // Custom panes sit just above the overlay pane (400), so reference layers draw over
    // the zone being edited but under the draw handles in the marker pane (600) -- the
    // vertices have to stay grabbable.
    const PANE_BASE = 401;
    const ORDER_KEY = "ot_map_layer_order";

    let layers_promise = null;
    const feature_cache = {};

    function get_layers() {
        if (!layers_promise) {
            layers_promise = frappe
                .xcall("organizer_toolkit.map_layers.get_layers")
                .catch(() => []);
        }
        return layers_promise;
    }

    function get_features(layer_name) {
        if (!feature_cache[layer_name]) {
            feature_cache[layer_name] = frappe
                .xcall("organizer_toolkit.map_layers.get_layer_features", { layer: layer_name })
                .catch(() => ({ features: [] }));
        }
        return feature_cache[layer_name];
    }

    // The colour is interpolated into SVG and into inline styles below, so only let
    // through what a colour can actually be. The Color control produces hex; anything
    // else came from an import or a hand-edited fixture.
    function safe_colour(value) {
        return /^(#[0-9a-f]{3,8}|[a-z]+)$/i.test(String(value || "")) ? value : DEFAULTS.color;
    }

    function style_of(layer) {
        return {
            color: safe_colour(layer.color),
            weight: layer.line_weight == null ? DEFAULTS.line_weight : layer.line_weight,
            fillColor: safe_colour(layer.color),
            fillOpacity: layer.fill_opacity == null ? DEFAULTS.fill_opacity : layer.fill_opacity,
        };
    }

    // A swatch and a pair of reorder arrows in the layer control, so a map with five
    // layers on is both readable and rearrangeable. Leaflet drops the overlay name into
    // innerHTML unescaped, which is what makes this possible -- and why everything
    // interpolated here is escaped or whitelisted first.
    function legend_label(layer, index, total) {
        const style = style_of(layer);
        const swatch =
            `<span style="display:inline-block;width:10px;height:10px;vertical-align:middle;` +
            `margin-right:5px;background:${style.fillColor};opacity:${Math.max(
                style.fillOpacity,
                0.35
            )};border:1px solid ${style.color};border-radius:${
                layer.marker_shape === "Square" ? "2px" : "50%"
            }"></span>`;

        const name = frappe.utils.escape_html(layer.layer_name);
        const tooltip = layer.description
            ? ` title="${frappe.utils.escape_html(layer.description)}"`
            : "";
        const id = frappe.utils.escape_html(layer.name);

        const arrow = (direction, glyph, disabled) =>
            `<span class="ot-layer-move" data-layer="${id}" data-dir="${direction}"
                   title="${__("Move {0}", [direction === "up" ? __("up") : __("down")])}"
                   style="cursor:pointer;padding:0 3px;opacity:${disabled ? 0.2 : 0.55};` +
            `pointer-events:${disabled ? "none" : "auto"}">${glyph}</span>`;

        return (
            `<span${tooltip}>${swatch}${name}</span>` +
            `<span style="float:right;margin-left:8px;white-space:nowrap">` +
            arrow("up", "&#9650;", index === 0) +
            arrow("down", "&#9660;", index === total - 1) +
            `</span>`
        );
    }

    // -- stacking order ------------------------------------------------------------

    function pane_name(layer) {
        return "ot-layer-" + String(layer.name).replace(/[^a-z0-9]+/gi, "-").toLowerCase();
    }

    function ensure_pane(map, layer) {
        const name = pane_name(layer);

        if (!map.getPane(name)) {
            map.createPane(name);
        }

        return name;
    }

    // First in the list draws on top, the way a layers panel usually reads. Changing a
    // pane's z-index restacks both vectors and markers with no redraw and no refetch.
    function apply_stacking(map, order) {
        order.forEach((layer, index) => {
            const pane = map.getPane(pane_name(layer));
            if (pane) {
                pane.style.zIndex = PANE_BASE + (order.length - index);
            }
        });
    }

    function saved_order() {
        try {
            return JSON.parse(localStorage.getItem(ORDER_KEY)) || [];
        } catch (e) {
            return [];
        }
    }

    function save_order(order) {
        try {
            localStorage.setItem(ORDER_KEY, JSON.stringify(order.map((layer) => layer.name)));
        } catch (e) {
            // Private browsing, or a full quota. The order just does not persist.
        }
    }

    // A viewer's own arrangement, on top of the shared display_order from the server. A
    // layer the saved order has never seen keeps its configured position, at the end.
    function apply_saved_order(layers) {
        const saved = saved_order();
        if (!saved.length) return layers;

        const rank = {};
        saved.forEach((name, index) => (rank[name] = index));

        return layers
            .slice()
            .sort(
                (a, b) =>
                    (rank[a.name] === undefined ? Infinity : rank[a.name]) -
                    (rank[b.name] === undefined ? Infinity : rank[b.name])
            );
    }

    function move(order, layer_name, direction) {
        const index = order.findIndex((layer) => layer.name === layer_name);
        const target = index + direction;

        if (index < 0 || target < 0 || target >= order.length) return false;

        [order[index], order[target]] = [order[target], order[index]];

        return true;
    }

    // Rebuilds the control's rows in the new order using its public API -- removeLayer
    // only unregisters from the control, it does not take the layer off the map, and the
    // checkbox state is derived from map.hasLayer, so ticks survive.
    function rebuild_rows(control, order, groups) {
        order.forEach((layer) => control.removeLayer(groups[layer.name]));
        order.forEach((layer, index) =>
            control.addOverlay(groups[layer.name], legend_label(layer, index, order.length))
        );
    }

    // -- saved maps ----------------------------------------------------------------
    //
    // Deliberately not wired into every map. A saved view is a destination -- it has its
    // own page at /app/ot-map/<name>, which drives these through the controller that
    // attach() hands back.

    function apply_saved_map(context, saved_map) {
        return frappe
            .xcall("organizer_toolkit.map_layers.get_saved_map", { saved_map: saved_map })
            .then((saved) => {
                const wanted = saved.layers || [];
                const rank = {};
                wanted.forEach((name, index) => (rank[name] = index));

                // Listed layers first, in their saved order; everything else keeps its
                // relative position underneath.
                context.order.sort(
                    (a, b) =>
                        (rank[a.name] === undefined ? Infinity : rank[a.name]) -
                        (rank[b.name] === undefined ? Infinity : rank[b.name])
                );

                apply_stacking(context.map, context.order);
                save_order(context.order);
                rebuild_rows(context.control, context.order, context.groups);

                context.order.forEach((layer) => {
                    const group = context.groups[layer.name];
                    const should_show = rank[layer.name] !== undefined;

                    if (should_show && !context.map.hasLayer(group)) {
                        group.addTo(context.map);
                    } else if (!should_show && context.map.hasLayer(group)) {
                        context.map.removeLayer(group);
                    }
                });

                if (saved.center_latitude && saved.center_longitude) {
                    context.map.setView(
                        [saved.center_latitude, saved.center_longitude],
                        saved.zoom || context.map.getZoom()
                    );
                } else if (saved.zoom) {
                    context.map.setZoom(saved.zoom);
                }

                context.applied = saved.map_name;

                return saved;
            });
    }

    function save_view(context, on_saved) {
        const centre = context.map.getCenter();
        const visible = context.order
            .filter((layer) => context.map.hasLayer(context.groups[layer.name]))
            .map((layer) => layer.name);

        frappe.prompt(
            [
                {
                    fieldname: "map_name",
                    fieldtype: "Data",
                    label: __("Name this view"),
                    reqd: 1,
                    default: context.applied || "",
                    description: __("{0} layer(s) showing, at zoom {1}", [
                        visible.length,
                        context.map.getZoom(),
                    ]),
                },
            ],
            (values) => {
                frappe
                    .xcall("organizer_toolkit.map_layers.save_current_view", {
                        map_name: values.map_name,
                        layers: visible,
                        center_latitude: centre.lat,
                        center_longitude: centre.lng,
                        zoom: context.map.getZoom(),
                    })
                    .then((saved) => {
                        context.applied = values.map_name;
                        frappe.show_alert({
                            message: __("Saved {0} with {1} layer(s)", [
                                saved.name,
                                saved.layers,
                            ]),
                            indicator: "green",
                        });
                        if (on_saved) on_saved(saved);
                    });
            },
            __("Save This View"),
            __("Save")
        );
    }

    // Circle is an L.circleMarker, which takes size and opacity directly. Pin and Square
    // are inline SVG in a divIcon -- passing className drops leaflet-div-icon's white box.
    function icon_for(layer) {
        const style = style_of(layer);
        const size = (layer.marker_size || DEFAULTS.marker_size) * 2;

        if (layer.marker_shape === "Square") {
            const inset = style.weight / 2;
            const html = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
                <rect x="${inset}" y="${inset}" width="${size - style.weight}"
                      height="${size - style.weight}" fill="${style.fillColor}"
                      fill-opacity="${style.fillOpacity}" stroke="${style.color}"
                      stroke-width="${style.weight}"/></svg>`;

            return L.divIcon({
                html: html,
                className: "ot-map-layer-icon",
                iconSize: [size, size],
                iconAnchor: [size / 2, size / 2],
            });
        }

        // Teardrop, anchored at its point rather than its centre.
        const height = size * 1.4;
        const html = `<svg width="${size}" height="${height}" viewBox="0 0 24 34">
            <path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 22 12 22s12-13 12-22c0-6.6-5.4-12-12-12z"
                  fill="${style.fillColor}" fill-opacity="${style.fillOpacity}"
                  stroke="${style.color}" stroke-width="${style.weight}"/>
            <circle cx="12" cy="12" r="4" fill="#fff" fill-opacity="0.85"/></svg>`;

        return L.divIcon({
            html: html,
            className: "ot-map-layer-icon",
            iconSize: [size, height],
            iconAnchor: [size / 2, height],
        });
    }

    function point_to_layer(layer, latlng, pane) {
        if (layer.marker_shape === "Circle" || !layer.marker_shape) {
            return L.circleMarker(latlng, {
                ...style_of(layer),
                radius: layer.marker_size || DEFAULTS.marker_size,
                pane: pane,
            });
        }
        return L.marker(latlng, { icon: icon_for(layer), pane: pane });
    }

    function bind_popup(layer, feature, target) {
        const properties = feature.properties || {};
        const label = properties.label || properties.name || layer.layer_name;

        let html = `<b>${frappe.utils.escape_html(String(label))}</b>`;

        if (layer.source_type === "DocType" && layer.source_doctype && properties.name) {
            html += `<div class="small mt-1">${frappe.utils.get_form_link(
                layer.source_doctype,
                properties.name,
                true,
                __("Open")
            )}</div>`;
        }

        target.bindPopup(html);
    }

    function render(group, layer, collection, pane) {
        group.addLayer(
            L.geoJSON(collection, {
                // Polygons pick the pane up from these options; points are built by
                // pointToLayer, so it has to be handed down explicitly.
                pane: pane,
                pointToLayer: (feature, latlng) => point_to_layer(layer, latlng, pane),
                style: () => style_of(layer),
                onEachFeature: (feature, target) => bind_popup(layer, feature, target),
            })
        );

        if (collection.truncated) {
            frappe.show_alert({
                message: __("{0}: showing the first {1} of {2}. Filter it down or raise Max Features.", [
                    layer.layer_name,
                    (collection.features || []).length,
                    collection.total,
                ]),
                indicator: "orange",
            });
        }
    }

    /**
     * Add the OT Map Layer control to a Leaflet map.
     *
     * @param {Object} map - a Leaflet map instance
     * @param {Object} [options]
     * @param {Function} [options.should_fit] - called after a layer loads; when it returns
     *   true the map is fitted to that layer. Used on an empty Geolocation field, where
     *   Frappe's own fit_and_recenter_map has no bounds to work with and silently leaves
     *   the map at the locality centre -- nowhere near the pins being drawn around.
     */
    organizer_toolkit.map_layers.attach = function (map, options) {
        options = options || {};

        if (typeof L === "undefined" || !map || map._ot_map_layers) {
            return Promise.resolve();
        }
        map._ot_map_layers = true;

        return get_layers().then((layers) => {
            if (!layers || !layers.length) return;

            const order = apply_saved_order(layers);
            const overlays = {};
            const groups = {};

            order.forEach((layer, index) => {
                // Empty on purpose: nothing is fetched until this group joins the map.
                const group = L.layerGroup();
                group._ot_layer = layer;
                group._ot_pane = ensure_pane(map, layer);
                groups[layer.name] = group;
                overlays[legend_label(layer, index, order.length)] = group;
            });

            apply_stacking(map, order);

            const control = L.control.layers(null, overlays, { position: "topright" });
            control.addTo(map);

            // Delegated, because rebuild_rows replaces every row on each move. Clicks
            // must not reach the label, or reordering would toggle the layer off.
            $(control.getContainer()).on("click", ".ot-layer-move", function (event) {
                event.preventDefault();
                event.stopPropagation();

                const button = $(this);
                const direction = button.attr("data-dir") === "up" ? -1 : 1;

                if (!move(order, button.attr("data-layer"), direction)) return;

                apply_stacking(map, order);
                save_order(order);
                rebuild_rows(control, order, groups);
            });

            // Leaflet's layer control fires overlayadd for programmatic adds too, so
            // show_by_default below comes through here as well.
            map.on("overlayadd", (event) => {
                const group = event.layer;
                if (!group || !group._ot_layer || group._ot_loaded) return;

                group._ot_loaded = true;
                const layer = group._ot_layer;

                get_features(layer.name).then((collection) => {
                    render(group, layer, collection, group._ot_pane);

                    if (options.should_fit && options.should_fit()) {
                        try {
                            map.fitBounds(group.getBounds(), { padding: [40, 40] });
                        } catch (e) {
                            // No bounds when the layer came back empty.
                        }
                    }
                });
            });

            const context = { map, control, order, groups, applied: null };

            // What the saved-map page drives. Ordinary maps ignore it and just get the
            // layer control.
            context.apply_saved_map = (saved_map) => apply_saved_map(context, saved_map);
            context.save_view = (on_saved) => save_view(context, on_saved);

            if (!options.defer_default_layers) {
                order
                    .filter((layer) => layer.show_by_default)
                    .forEach((layer) => groups[layer.name].addTo(map));
            }

            return context;
        });
    };

    // Layers are configured rarely and read constantly, so both lists are cached for the
    // session. Saving an OT Map Layer drops the cache (see ot_map_layer.js).
    organizer_toolkit.map_layers.clear_cache = function () {
        layers_promise = null;
        Object.keys(feature_cache).forEach((key) => delete feature_cache[key]);
    };

    // -- Integration points --------------------------------------------------------

    // The Geolocation field, which is where turf actually gets cut.
    if (frappe.ui.form.ControlGeolocation && !frappe.ui.form.ControlGeolocation._ot_patched) {
        frappe.ui.form.ControlGeolocation._ot_patched = true;

        const make_map = frappe.ui.form.ControlGeolocation.prototype.make_map;

        frappe.ui.form.ControlGeolocation.prototype.make_map = function (value) {
            make_map.call(this, value);

            // Reference layers go on the map, NEVER on this.editableLayers. A draw event
            // serialises editableLayers straight into the field value (geolocation.js
            // bind_leaflet_event_listeners), so a lot pin added there would be saved as
            // part of the zone boundary.
            organizer_toolkit.map_layers.attach(this.map, {
                should_fit: () => !this.editableLayers || !this.editableLayers.getLayers().length,
            });
        };
    }

    // Every list Map View. Safe to reassign: list_factory.js resolves
    // frappe.views[view_name + "View"] at route time, and app_include_js loads after the
    // desk bundle.
    if (frappe.views && frappe.views.MapView && !frappe.views.MapView._ot_patched) {
        const BaseMapView = frappe.views.MapView;

        frappe.views.MapView = class OTMapView extends BaseMapView {
            setup_view() {
                super.setup_view();
                organizer_toolkit.map_layers.attach(this.map);
            }
        };
        frappe.views.MapView._ot_patched = true;
    }
})();
