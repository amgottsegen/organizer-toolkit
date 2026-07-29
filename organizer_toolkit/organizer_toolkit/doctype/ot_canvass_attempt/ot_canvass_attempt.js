// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.ui.form.on("OT Canvass Attempt", {
    setup: function(frm) {
        // A canvasser at a door should only be offered petitions still being collected
        // and events that have not happened yet.
        // Linking someone already in the system is rare at a door, and when it does
        // happen it is almost always a person already recorded at *this* address. So
        // scope the dropdown to that rather than listing every constituent: at a new
        // door it comes back empty and "Create a new Constituent" is the only option,
        // and at a known door it shows the handful of people who live there.
        frm.set_query("constituent", () =>
            frm.doc.address ? { filters: { address: frm.doc.address } } : {}
        );

        frm.set_query("petition_signed", () => ({ filters: { is_active: 1 } }));
        frm.set_query("event_rsvp", () => ({
            filters: { event_start: [">=", frappe.datetime.get_today()] },
        }));
    },

    onload: function(frm) {
        // The doorknocking map deep-links here with a street rather than an address ID,
        // since the map's pins come from city property data that has no OT Address yet.
        const street = frappe.route_options && frappe.route_options.address_line_1;
        if (!street || frm.doc.address) return;

        delete frappe.route_options.address_line_1;

        frappe.call({
            method: "organizer_toolkit.organizer_toolkit.doctype.ot_canvass_attempt.ot_canvass_attempt.resolve_address",
            args: { address_line_1: street },
            callback(r) {
                if (r.message) frm.set_value("address", r.message.name);
            },
        });
    },

    refresh: function(frm) {
        if (!frm.is_new() || frm.doc.address) {
            show_address_history(frm);
        }

        // The overwhelmingly common case at a door: somebody answered and they are not
        // in the system yet. Make that one tap instead of open-dropdown-then-create.
        if (frm.doc.outcome === "Answered" && !frm.doc.constituent) {
            frm.add_custom_button(__('Add Person'), () => {
                frappe.ui.form.make_quick_entry("OT Constituent", (doc) => {
                    if (doc && doc.name) frm.set_value("constituent", doc.name);
                });
            }).addClass("btn-primary");
        }

        if (frm.doc.address) {
            frm.add_custom_button(__('Open Address'), () => {
                frappe.set_route("Form", "OT Address", frm.doc.address);
            }, __('Actions'));
        }

        if (frm.doc.constituent) {
            frm.add_custom_button(__('Open Constituent'), () => {
                frappe.set_route("Form", "OT Constituent", frm.doc.constituent);
            }, __('Actions'));
        }
    },

    address: function(frm) {
        show_address_history(frm);
    },

    before_save: function(frm) {
        // after_save fires for edits too, and by then the record is no longer new --
        // so remember here whether this save is the one that created it.
        frm.__created_by_this_save = frm.is_new();
    },

    after_save: function(frm) {
        // Canvassers log a door and move straight to the next one; landing on the saved
        // record is a dead end they have to navigate out of. Editing an existing visit
        // still leaves you on it.
        if (!frm.__created_by_this_save) return;

        frm.__created_by_this_save = false;
        frappe.set_route("List", frm.doctype);
    },

    constituent: function(frm) {
        // Recording who you spoke to means somebody answered. Filled only when blank so
        // an explicit "Not interested" is never clobbered.
        if (frm.doc.constituent && !frm.doc.outcome) {
            frm.set_value("outcome", "Answered");
        }
    },
});

// Knowing this door was already knocked -- and how it went -- is the difference between
// a useful conversation and annoying someone twice in a week.
function show_address_history(frm) {
    if (!frm.doc.address) {
        frm.dashboard.clear_headline();
        return;
    }

    frappe.call({
        method: "organizer_toolkit.organizer_toolkit.doctype.ot_canvass_attempt.ot_canvass_attempt.get_address_history",
        args: { address: frm.doc.address },
        callback(r) {
            const history = (r.message || []).filter(v => v.name !== frm.doc.name);

            if (!history.length) {
                frm.dashboard.set_headline(
                    __("No previous visits recorded at this address."), "blue"
                );
                return;
            }

            const rows = history.slice(0, 5).map(v => {
                const when = frappe.datetime.str_to_user(v.canvassed_on);
                const note = v.notes ? ` &mdash; ${frappe.utils.escape_html(v.notes)}` : "";
                return `<li><b>${frappe.utils.escape_html(v.outcome || "")}</b> on ${when}${note}</li>`;
            }).join("");

            frm.dashboard.set_headline(
                `<b>${history.length}</b> previous visit(s) at this address:<ul>${rows}</ul>`,
                "orange"
            );
        },
    });
}
