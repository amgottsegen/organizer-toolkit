// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.ui.form.on("OT Address", {
    refresh: function(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__('Geocode'), function() {
            frappe.call({
                method: "organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address.geocode_address",
                args: { doc_name: frm.doc.name },
                freeze: true,
                freeze_message: __("Geocoding address..."),
                callback(r) {
                    if (!r.message) return;
                    frappe.show_alert({
                        message: __("Address geocoded"),
                        indicator: "green",
                    });
                    frm.reload_doc();
                }
            });
        }, __('Actions'));
    }
});
