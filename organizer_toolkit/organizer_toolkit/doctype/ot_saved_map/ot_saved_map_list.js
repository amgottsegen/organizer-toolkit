// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.listview_settings["OT Saved Map"] = {
    add_fields: ["enabled"],

    get_indicator: function(doc) {
        return doc.enabled
            ? [__("Enabled"), "green", "enabled,=,1"]
            : [__("Disabled"), "gray", "enabled,=,0"];
    },

    // The list is where you pick a view; the point of picking one is to look at it, not
    // to edit its layer table.
    button: {
        show: () => true,
        get_label: () => __("Open Map"),
        get_description: (doc) => __("Open {0}", [doc.map_name]),
        action: (doc) => frappe.set_route("ot-map", doc.name),
    },

    onload: function(listview) {
        listview.page.add_inner_button(__("New Map View"), () => {
            frappe.set_route("ot-map");
        });
    },
};
