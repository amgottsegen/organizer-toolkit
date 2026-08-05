// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.listview_settings["OT Address"] = frappe.listview_settings["OT Address"] || {};

frappe.listview_settings["OT Address"].onload = function(listview) {
    listview.page.add_actions_menu_item("Geocode Addresses", () => geocodeSelectedAddresses(listview));

    // Filter the list however you like -- one street, one ZIP, everything not knocked
    // this month -- tick the doors and turn them into a route. The zone path only covers
    // "everything inside this boundary".
    if (frappe.model.can_create("OT Walk List")) {
        listview.page.add_actions_menu_item(__("Create Walk List"), () => createWalkList(listview));
    }
};

function geocodeSelectedAddresses(listview) {
    const selected = listview.get_checked_items();

    if (!selected.length) {
        frappe.msgprint("Please select at least one address.");
        return;
    }
    if (selected.length > 10) {
        frappe.throw("Please select no more than 10 addresses at a time to avoid hitting geocoding rate limits.");
    }

    frappe.confirm(
        `Geocode <strong>${selected.length} selected address(es)</strong>?`,
        () => {
            const calls = selected.map(r =>
                frappe.call({
                    method: "organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address.geocode_address",
                    args: { doc_name: r.name },
                })
            );

            Promise.all(calls).then(() => {
                frappe.show_alert({
                    message: `Geocoded ${selected.length} address(es)`,
                    indicator: "green",
                });
                listview.refresh();
            });
        }
    );
}

function createWalkList(listview) {
    const selected = listview.get_checked_items(true);

    if (!selected.length) {
        frappe.msgprint(__("Please select at least one address."));
        return;
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Create Walk List"),
        fields: [
            {
                fieldname: "summary",
                fieldtype: "HTML",
                options: `<p class="text-muted">${__("{0} door(s) selected.", [
                    selected.length,
                ])}</p>`,
            },
            {
                fieldname: "list_name",
                fieldtype: "Data",
                label: __("List Name"),
                reqd: 1,
                default: __("Walk List {0}", [frappe.datetime.get_today()]),
            },
            {
                fieldname: "canvass_date",
                fieldtype: "Date",
                label: __("Canvass Date"),
                default: frappe.datetime.get_today(),
            },
            {
                fieldname: "assigned_to",
                fieldtype: "Link",
                label: __("Assigned To"),
                options: "User",
            },
            {
                fieldname: "zone",
                fieldtype: "Link",
                label: __("Canvass Zone"),
                options: "OT Canvass Zone",
                // Not just bookkeeping: every doorknock logged from this list takes its
                // zone from here, and that is the only record of which turf the work
                // belonged to once boundaries are redrawn.
                description: __("Labels every doorknock logged from this list."),
            },
        ],
        primary_action_label: __("Create"),
        primary_action(values) {
            dialog.disable_primary_action();

            frappe.call({
                method: "organizer_toolkit.organizer_toolkit.doctype.ot_walk_list.ot_walk_list.create_from_addresses",
                args: {
                    addresses: selected,
                    list_name: values.list_name,
                    canvass_date: values.canvass_date,
                    assigned_to: values.assigned_to,
                    zone: values.zone,
                },
                freeze: true,
                freeze_message: __("Building the walk list..."),
                callback(r) {
                    if (!r.message) return;

                    dialog.hide();
                    frappe.show_alert({
                        message: __("Walk list created with {0} door(s)", [r.message.total]),
                        indicator: "green",
                    });
                    listview.clear_checked_items();
                    // Straight to the list -- the next step is nearly always assigning it
                    // or reordering the doors.
                    frappe.set_route("Form", "OT Walk List", r.message.name);
                },
                always() {
                    dialog.enable_primary_action();
                },
            });
        },
    });

    dialog.show();
}
