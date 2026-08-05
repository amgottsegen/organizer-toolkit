// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.ui.form.on("OT Saved Map", {
    refresh: function(frm) {
        if (frm.is_new()) {
            frm.dashboard.set_headline(
                __("Easier to build these from the map itself: arrange the layers you want, then use <b>Save View</b>."),
                "blue"
            );
            return;
        }

        // Each saved view has a page of its own, so this is a link to a place rather
        // than a mode toggle -- the URL can be shared and bookmarked.
        frm.add_custom_button(__('Open Map'), () => {
            frappe.set_route("ot-map", frm.doc.name);
        }).addClass("btn-primary");

        frm.dashboard.set_headline(
            __("Opens at <a href='/app/ot-map/{0}'>/app/ot-map/{0}</a>", [
                encodeURIComponent(frm.doc.name),
            ]),
            "blue"
        );
    },
});
