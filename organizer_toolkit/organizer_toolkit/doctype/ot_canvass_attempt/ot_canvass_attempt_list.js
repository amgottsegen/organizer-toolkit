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

    onload: function(listview) {
        add_rapid_entry_button(listview);
        add_my_doorknocks_toggle(listview);
        add_map_button(listview);
    },
};

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

// filter_area.get() yields [doctype, fieldname, operator, value].
function current_filter_value(listview, fieldname) {
    const filter = listview.filter_area
        .get()
        .find((f) => f[1] === fieldname && f[2] === "=");

    return filter ? filter[3] : null;
}

// The sidebar's "Created By" grouping only exists on desktop -- the whole side section
// is dropped on small screens, which is also why the Map link is unreachable there. For
// a canvasser on a phone this button is the only way to see just their own work.
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
        add_rapid_entry_button(listview);
        add_my_doorknocks_toggle(listview);
        add_map_button(listview);
    });
}

function add_map_button(listview) {
    listview.page.add_inner_button(__("Map"), function() {
        frappe.set_route("List", listview.doctype, "Map");
    });
}
