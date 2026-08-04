// Copyright (c) 2026, CREATE Lab and contributors
// For license information, please see license.txt

frappe.ui.form.on("OT Map Layer", {
    onload: function(frm) {
        // Only doctypes a map can actually plot -- a Geolocation field named location, or
        // a latitude/longitude pair.
        frappe.xcall("organizer_toolkit.map_layers.get_mappable_doctypes").then((names) => {
            frm.set_query("source_doctype", () => ({ filters: { name: ["in", names] } }));
        });
    },

    refresh: function(frm) {
        render_filters(frm);

        if (!frm.is_new()) {
            frm.add_custom_button(__('Preview on Map'), () => {
                frappe.set_route("List", frm.doc.source_doctype || "OT Address", "Map");
            });
        }
    },

    source_type: function(frm) {
        render_filters(frm);
    },

    source_doctype: function(frm) {
        // Filters are written against one doctype's fields; keeping them would leave
        // conditions naming columns the new doctype does not have.
        frm.set_value("filters_json", "[]");
        render_filters(frm);
    },

    after_save: function(frm) {
        // The layer list and its features are cached for the session, so an edit would
        // otherwise not show up on a map until reload.
        organizer_toolkit.map_layers &&
            organizer_toolkit.map_layers.clear_cache &&
            organizer_toolkit.map_layers.clear_cache();
    },
});

// Replaces the raw JSON editor with a table that opens a real filter builder, the same
// trade the Dashboard Chart form makes (frappe/desk/doctype/dashboard_chart).
function render_filters(frm) {
    const field = frm.get_field("filters_json");
    if (!field) return;

    const wrapper = $(field.wrapper).empty();

    if (frm.doc.source_type !== "DocType" || !frm.doc.source_doctype) {
        $(`<p class="text-muted small">${__("Pick a source doctype to filter it.")}</p>`).appendTo(
            wrapper
        );
        return;
    }

    const filters = parse_filters(frm);

    // Warm the source doctype's meta now so clicking the table opens a filter builder
    // that already knows the fields. with_doctype is a no-op once it has been loaded.
    frappe.model.with_doctype(frm.doc.source_doctype);

    const table = $(`<table class="table table-bordered" style="cursor:pointer; margin:0px;">
        <thead>
            <tr>
                <th style="width: 30%">${__("Field")}</th>
                <th style="width: 25%">${__("Condition")}</th>
                <th>${__("Value")}</th>
            </tr>
        </thead>
        <tbody></tbody>
    </table>`).appendTo(wrapper);

    if (filters.length) {
        filters.forEach((filter) => {
            $(`<tr>
                <td>${frappe.utils.escape_html(String(filter[1]))}</td>
                <td>${frappe.utils.escape_html(String(filter[2] || "="))}</td>
                <td>${frappe.utils.escape_html(String(filter[3]))}</td>
            </tr>`).appendTo(table.find("tbody"));
        });
    } else {
        $(`<tr><td colspan="3" class="text-muted text-center">
            ${__("No filters — the whole doctype. Click to set filters.")}</td></tr>`).appendTo(
            table.find("tbody")
        );
    }

    $(`<p class="text-muted small">${__("Click the table to edit")}</p>`).appendTo(wrapper);

    table.on("click", () => open_filter_dialog(frm, filters));
}

function parse_filters(frm) {
    try {
        return JSON.parse(frm.doc.filters_json || "[]") || [];
    } catch (e) {
        return [];
    }
}

function open_filter_dialog(frm, filters) {
    // FieldSelect builds its list of filterable fields from
    // frappe.meta.docfield_list[doctype], which is only populated once that doctype's
    // meta has been loaded into the client. Nothing on this form loads OT Address (or
    // whichever source doctype), so without this the builder opens with nothing to
    // filter on -- it is not that the fields are hidden, it is that the client has
    // never been told they exist.
    frappe.model.with_doctype(frm.doc.source_doctype, () => {
        const dialog = new frappe.ui.Dialog({
            title: __("Set Filters"),
            fields: [{ fieldtype: "HTML", fieldname: "filter_area" }],
            primary_action_label: __("Set"),
            primary_action: () => {
                frm.set_value("filters_json", JSON.stringify(frm.filter_group.get_filters()));
                dialog.hide();
                render_filters(frm);
            },
        });

        frm.filter_group = new frappe.ui.FilterGroup({
            parent: dialog.get_field("filter_area").$wrapper,
            doctype: frm.doc.source_doctype,
            on_change: () => {},
        });

        frm.filter_group.add_filters_to_filter_group(filters);
        dialog.show();
    });
}
