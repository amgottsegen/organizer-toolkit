// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.listview_settings["OT Constituent"] = {
    hide_name_column: true,
    hide_name_filter: true
};

frappe.listview_settings["OT Constituent"] = frappe.listview_settings["OT Constituent"] || {};


frappe.listview_settings["OT Constituent"].onload = function(listview) {
    listview.page.add_actions_menu_item("Clear Tags", () => showClearTagsDialog(listview));
    listview.page.add_actions_menu_item("Geocode Addresses", () => geocodeSelected(listview));

    listview.page.add_inner_button(__("Filter by Event"), () => showEventFilterDialog(listview));
    listview.page.add_inner_button(__("Filter by Activity"), () => showActivityFilterDialog(listview));
};

// Event RSVPs and volunteer interests are their own doctypes now, which is what lets a
// canvasser record one without write access to the whole person. The cost is that Frappe
// cannot filter this list across the link: db_query joins child tables on
// parent/parenttype and link fields forwards only, so there is no "constituents whose
// RSVP..." condition to write. Both buttons below resolve the question on the server and
// apply the answer as `name in (...)`, which is the only shape a list view accepts.
function applyNameFilter(listview, names, empty_message) {
    if (!names.length) {
        frappe.msgprint(empty_message);
        return;
    }

    listview.filter_area.remove("name").then(() => {
        listview.filter_area.add([[listview.doctype, "name", "in", names]]);
    });
}

function showEventFilterDialog(listview) {
    const dialog = new frappe.ui.Dialog({
        title: __("Filter by Event RSVP"),
        fields: [
            {
                fieldname: "event",
                fieldtype: "Link",
                label: __("Event"),
                options: "OT Event",
                reqd: 1,
            },
            {
                fieldname: "rsvp",
                fieldtype: "Select",
                label: __("RSVP"),
                options: "\nYes\nMaybe\nNo",
                description: __("Leave blank for anyone invited, however they answered."),
            },
            {
                fieldname: "attended",
                fieldtype: "Check",
                label: __("Attended only"),
            },
        ],
        primary_action_label: __("Apply"),
        primary_action(values) {
            frappe
                .xcall(
                    "organizer_toolkit.organizer_toolkit.doctype.ot_event_rsvp.ot_event_rsvp.constituents_for_event",
                    {
                        event: values.event,
                        rsvp: values.rsvp || null,
                        attended: values.attended ? 1 : null,
                    }
                )
                .then((names) => {
                    dialog.hide();
                    applyNameFilter(
                        listview,
                        names,
                        __("Nobody matches that event and RSVP.")
                    );
                });
        },
    });

    dialog.show();
}

function showActivityFilterDialog(listview) {
    const dialog = new frappe.ui.Dialog({
        title: __("Filter by Volunteer Interest"),
        fields: [
            {
                fieldname: "activity",
                fieldtype: "Link",
                label: __("Activity"),
                options: "OT Activity",
                reqd: 1,
            },
        ],
        primary_action_label: __("Apply"),
        primary_action(values) {
            frappe
                .xcall("frappe.client.get_list", {
                    doctype: "OT Volunteer Interest",
                    filters: { activity: values.activity },
                    fields: ["constituent"],
                    limit_page_length: 0,
                })
                .then((rows) => {
                    dialog.hide();
                    applyNameFilter(
                        listview,
                        [...new Set(rows.map((row) => row.constituent))],
                        __("Nobody has offered to help with that yet.")
                    );
                });
        },
    });

    dialog.show();
}

function geocodeSelected(listview) {
    const selected = listview.get_checked_items();

    if (!selected.length) {
        frappe.msgprint("Please select at least one constituent.");
        return;
    }

    const missing = selected.filter(r => !r.address).length;
    // Geocoding now happens on OT Address. Several constituents can share one door, so
    // collapse to distinct addresses -- otherwise a household burns one geocoding
    // request per member for the same coordinates.
    const addresses = [...new Set(selected.filter(r => r.address).map(r => r.address))];

    if (!addresses.length) {
        frappe.msgprint("None of the selected constituents have an address linked.");
        return;
    }
    if (addresses.length > 10) {
        frappe.throw("Please select no more than 10 distinct addresses at a time to avoid hitting geocoding rate limits.");
    }

    const note = missing ? `<br><em>${missing} selected record(s) have no address and will be skipped.</em>` : "";

    frappe.confirm(
        `Geocode <strong>${addresses.length} address(es)</strong> for ${selected.length} selected record(s)?${note}`,
        () => {
            const calls = addresses.map(name =>
                frappe.call({
                    method: "organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address.geocode_address",
                    args: { doc_name: name },
                })
            );

            Promise.all(calls).then(() => {
                frappe.show_alert({
                    message: `Geocoded ${addresses.length} address(es)`,
                    indicator: "green",
                });
                listview.refresh();
            });
        }
    );
}

function showClearTagsDialog(listview) {
    const selected = listview.get_checked_items();

    if (!selected.length) {
        frappe.msgprint("Please select at least one constituent.");
        return;
    }

    const selectedNames = selected.map(r => r.name);

    // Fetch tags present on the selected docs only
    frappe.call({
        method: "organizer_toolkit.api.get_tags_for_docs",
        args: {
            doctype: "OT Constituent",
            doc_names: JSON.stringify(selectedNames),
        },
        callback(r) {
            const allTags = (r.message || []).map(t => ({ label: t, value: t }));

            if (!allTags.length) {
                frappe.msgprint("No tags found on the selected records.");
                return;
            }

            const dialog = new frappe.ui.Dialog({
                title: "Clear Tags",
                fields: [
                    {
                        fieldname: "info",
                        fieldtype: "HTML",
                        options: `<p class="text-muted">
                            Select tags to remove from the
                            <strong>${selectedNames.length} selected record(s)</strong>.
                        </p>`,
                    },
                    {
                        fieldname: "tags",
                        label: "Tags to Clear",
                        fieldtype: "MultiSelectPills",
                        options: allTags,
                        reqd: 1,
                    },
                ],
                primary_action_label: "Clear Tags",
                primary_action(values) {
                    if (!values.tags || !values.tags.length) {
                        frappe.msgprint("Please select at least one tag.");
                        return;
                    }

                    frappe.confirm(
                        `Remove tag(s) <strong>${values.tags.join(", ")}</strong> from 
                        <strong>${selectedNames.length} selected record(s)</strong>?`,
                        () => {
                            frappe.call({
                                method: "organizer_toolkit.api.remove_tags_from_docs",
                                args: {
                                    tags: JSON.stringify(values.tags),
                                    doctype: "OT Constituent",
                                    doc_names: JSON.stringify(selectedNames),
                                },
                                callback(r) {
                                    frappe.show_alert({
                                        message: `Cleared: ${r.message.removed.join(", ")}`,
                                        indicator: "green",
                                    });
                                    dialog.hide();
                                    listview.refresh();
                                },
                            });
                        }
                    );
                },
            });

            dialog.show();
        },
    });
}

