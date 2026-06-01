// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.ui.form.on("OT Constituent", {
    refresh: function(frm) {
        // Syntax: frm.add_custom_button(__('Label'), action_function, group)
        frm.add_custom_button(__('Geocode'), (function() {
            frappe.call({
                                method: "organizer_toolkit.organizer_toolkit.doctype.ot_constituent.ot_constituent.geocode_address",
                                args: { doc_name: frm.doc.name },
                                freeze: true,
                                freeze_message: "Geocoding address...",
                                callback(r) {
                                    frappe.show_alert({
                                        message: `Success! Address geocoded.`,
                                        indicator: "green",
                                    });
                                    console.log(r.message);
                                    frm.reload_doc();
                                }})
        }), __('Actions')); // Optional: places the button under the 'Actions' dropdown
    }
});



