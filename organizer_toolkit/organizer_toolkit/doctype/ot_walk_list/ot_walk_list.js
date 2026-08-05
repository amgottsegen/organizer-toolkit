// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.ui.form.on("OT Walk List", {
    refresh: function(frm) {
        if (frm.is_new()) return;

        show_progress(frm);

        if (frm.doc.zone) {
            frm.add_custom_button(__('Populate from Zone'), () => populate_from_zone(frm));
        }

        // The list is the better place to work from: it shows what has been knocked so
        // far, and its own Rapid Entry picks the walk list up from this filter, so doors
        // logged there still count toward this list.
        frm.add_custom_button(__('Go To Canvass Log'), () => {
            frappe.set_route("List", "OT Canvass Attempt", { walk_list: frm.doc.name });
        }).addClass("btn-primary");

        frm.add_custom_button(__('Map'), () => {
            frappe.set_route("List", "OT Canvass Attempt", "Map", { walk_list: frm.doc.name });
        }, __('View'));
    },
});

// Progress is derived from canvass attempts rather than stored on the rows -- a status
// field would drift the moment a door was logged outside this walk list.
function show_progress(frm) {
    frappe.call({
        method: "organizer_toolkit.organizer_toolkit.doctype.ot_walk_list.ot_walk_list.get_progress",
        args: { walk_list: frm.doc.name },
        callback(r) {
            const p = r.message;
            if (!p || !p.total) {
                frm.dashboard.set_headline(
                    __("No doors on this list yet. Use Populate from Zone, or add addresses below."),
                    "blue"
                );
                return;
            }

            const pct = Math.round((p.knocked / p.total) * 100);
            const colour = p.knocked === p.total ? "green" : p.knocked ? "orange" : "blue";

            frm.dashboard.set_headline(
                `<b>${p.knocked}</b> of <b>${p.total}</b> ${__("doors knocked")} (${pct}%)`,
                colour
            );
        },
    });
}

function populate_from_zone(frm) {
    frappe.confirm(
        __("Add every geocoded address inside <strong>{0}</strong> to this walk list?", [
            frm.doc.zone,
        ]),
        () => {
            frappe.call({
                method: "organizer_toolkit.organizer_toolkit.doctype.ot_walk_list.ot_walk_list.populate_from_zone",
                args: { walk_list: frm.doc.name },
                freeze: true,
                freeze_message: __("Finding addresses in the zone..."),
                callback(r) {
                    if (!r.message) return;
                    frappe.show_alert({
                        message: __("Added {0} door(s); {1} on the list", [
                            r.message.added,
                            r.message.total,
                        ]),
                        indicator: r.message.added ? "green" : "blue",
                    });
                    frm.reload_doc();
                },
            });
        }
    );
}
