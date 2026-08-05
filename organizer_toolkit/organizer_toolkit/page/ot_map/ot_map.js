// A saved map view as a place you can go: /app/ot-map/<saved map name>.
//
// The layer control that shows up on every Geolocation field and list Map View is the
// same one -- what is different here is that the whole page is the map, and the saved
// view is the thing being looked at rather than a widget bolted onto someone else's map.

frappe.pages["ot-map"].on_page_load = function(wrapper) {
    frappe.ot_map = new OTMapPage(wrapper);
};

frappe.pages["ot-map"].on_page_show = function() {
    frappe.ot_map && frappe.ot_map.show_route();
};

class OTMapPage {
    constructor(wrapper) {
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Map"),
            single_column: true,
        });

        this.map_id = frappe.dom.get_unique_id();
        this.applied = null;

        // Fill what is left of the window. The desk header and page head are fixed
        // height, so a viewport-relative height beats measuring the parent.
        $(this.page.main).html(
            `<div id="${this.map_id}" style="height:calc(100vh - 170px);min-height:320px;
                 border-radius:var(--border-radius-md);overflow:hidden"></div>`
        );

        this.setup_map();
        this.setup_actions();

        this.ready = organizer_toolkit.map_layers
            .attach(this.map, { defer_default_layers: true })
            .then((context) => {
                this.context = context;
                return context;
            });

        this.show_route();
    }

    setup_map() {
        L.Icon.Default.imagePath = frappe.utils.map_defaults.image_path;

        this.map = L.map(this.map_id).setView(
            frappe.utils.map_defaults.center,
            frappe.utils.map_defaults.zoom
        );

        L.tileLayer(frappe.utils.map_defaults.tiles, frappe.utils.map_defaults.options).addTo(
            this.map
        );

        L.control.scale().addTo(this.map);
        L.control.locate({ position: "topright" }).addTo(this.map);
    }

    setup_actions() {
        this.page.set_primary_action(
            __("Save View"),
            () => {
                if (!this.context) return;
                this.context.save_view((saved) => {
                    // The saved view now has an address of its own; go and be there, so
                    // the URL matches what is on screen.
                    frappe.set_route("ot-map", saved.name);
                });
            },
            "add"
        );

        this.page.add_menu_item(__("All Saved Views"), () =>
            frappe.set_route("List", "OT Saved Map")
        );

        this.page.add_menu_item(__("Edit This View"), () => {
            if (!this.applied) {
                frappe.msgprint(__("Open a saved view first."));
                return;
            }
            frappe.set_route("Form", "OT Saved Map", this.applied);
        });

        this.page.add_menu_item(__("Manage Layers"), () =>
            frappe.set_route("List", "OT Map Layer")
        );
    }

    show_route() {
        const saved_map = frappe.get_route()[1];

        // Leaflet measures the container when it is created. On a page that was built
        // while hidden -- or returned to from another route -- that measurement is stale.
        setTimeout(() => this.map && this.map.invalidateSize(), 100);

        if (!saved_map) {
            this.applied = null;
            this.page.set_title(__("Map"));
            this.page.set_indicator(__("No saved view"), "gray");
            this.show_default_layers();
            return;
        }

        if (saved_map === this.applied) return;

        this.ready.then((context) => {
            if (!context) return;

            context
                .apply_saved_map(saved_map)
                .then((saved) => {
                    this.applied = saved.name;
                    this.page.set_title(saved.map_name);
                    this.page.set_indicator(
                        __("{0} layer(s)", [saved.layers.length]),
                        "blue"
                    );
                })
                .catch(() => {
                    // Deleted, renamed, or not readable by this user.
                    this.page.set_indicator(__("Not found"), "red");
                });
        });
    }

    // Only when no saved view is being shown -- a saved view decides for itself what is
    // on, and letting the defaults in first would make them flash up and vanish.
    show_default_layers() {
        this.ready.then((context) => {
            if (!context || this.shown_defaults) return;
            this.shown_defaults = true;

            context.order
                .filter((layer) => layer.show_by_default)
                .forEach((layer) => context.groups[layer.name].addTo(this.map));
        });
    }
}
