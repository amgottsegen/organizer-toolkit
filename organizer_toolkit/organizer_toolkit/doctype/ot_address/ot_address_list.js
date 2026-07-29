// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.listview_settings["OT Address"] = frappe.listview_settings["OT Address"] || {};

frappe.listview_settings["OT Address"].onload = function(listview) {
    listview.page.add_actions_menu_item("Geocode Addresses", () => geocodeSelectedAddresses(listview));
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
