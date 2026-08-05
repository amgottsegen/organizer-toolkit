// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.listview_settings["OT Canvass Attempt"] = {
    add_fields: ["outcome", "owner", "location"],

    // Outcome is what you scan a canvass list for -- who knocked is one filter away,
    // via "My Doorknocks" below or the sidebar's Created By grouping.
    get_indicator: function(doc) {
        const colours = {
            "Answered": "green",
            "No answer": "gray",
            "Not interested": "red",
            "Abandoned": "orange",
        };
        return [
            __(doc.outcome || "No outcome"),
            colours[doc.outcome] || "gray",
            "outcome,=," + doc.outcome,
        ];
    },

    // Runs on the map view too -- see the MapView patch in public/js/map_layers.js.
    onload: function(listview) {
        add_toolbar(listview);
    },
};

function add_toolbar(listview) {
    add_rapid_entry_button(listview);
    add_my_doorknocks_toggle(listview);
    add_view_switch_button(listview);
}

function add_rapid_entry_button(listview) {
    listview.page.add_inner_button(__("Rapid Entry"), function() {
        organizer_toolkit.rapid_block_entry({
            // Filtering the list to a walk list is a statement about what you are
            // working on -- Frappe already carries that into a new document as a
            // default, so the dialog has to carry it too or the doors it logs go
            // uncounted against the list they were knocked for.
            walk_list: current_filter_value(listview, "walk_list"),
            on_save: () => listview.refresh(),
        });
    }).addClass("btn-primary");
}

// The sidebar's "Created By" grouping only exists on desktop -- the whole side section
// is dropped on small screens, which is also why the view links are unreachable there.
// For a canvasser on a phone this button is the only way to see just their own work.
function add_my_doorknocks_toggle(listview) {
    const FIELD = "owner";

    const is_active = () =>
        listview.filter_area
            .get()
            .some((f) => f[1] === FIELD && String(f[3]) === frappe.session.user);

    const label = () => (is_active() ? __("Show All Doorknocks") : __("My Doorknocks"));

    listview.page.add_inner_button(label(), function() {
        if (is_active()) {
            listview.filter_area.remove(FIELD);
        } else {
            listview.filter_area.add([
                [listview.doctype, FIELD, "=", frappe.session.user],
            ]);
        }
        // Rebuild so the button reflects the state it just moved to.
        listview.page.clear_inner_toolbar();
        add_toolbar(listview);
    });
}

// Switching views loses your filters: view_user_settings is keyed by view name
// (list_view.js), so the list and the map each remember their own set. Carrying the
// current filters across as route options closes that -- before_refresh clears the
// target view's filter area and applies these instead.
function add_view_switch_button(listview) {
    const on_map = listview.view_name === "Map";

    listview.page.add_inner_button(on_map ? __("List") : __("Map"), function() {
        const filters = route_filters(listview);

        if (on_map) {
            frappe.set_route("List", listview.doctype, filters);
        } else {
            frappe.set_route("List", listview.doctype, "Map", filters);
        }
    });
}

// filter_area.get() yields [doctype, fieldname, operator, value].
function route_filters(listview) {
    const filters = {};

    listview.filter_area.get().forEach(([doctype, fieldname, operator, value]) => {
        // Route options address the doctype's own columns; a filter reaching into a
        // child table has no representation here and is dropped rather than mangled.
        if (doctype !== listview.doctype) return;

        filters[fieldname] = operator === "=" ? value : [operator, value];
    });

    return filters;
}

function current_filter_value(listview, fieldname) {
    const filter = listview.filter_area
        .get()
        .find((f) => f[1] === fieldname && f[2] === "=");

    return filter ? filter[3] : null;
}
