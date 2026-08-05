// Rapid block entry: the fast path for working every door on one street.
//
// The street, city, state and postal code are typed once and stay put; each door is then
// a house number plus an outcome. The dialog never closes between doors, so there is no
// navigation and no re-picking of an address -- log_visit deduplicates on the normalized
// address key, so an address that already exists is reused rather than twinned.

frappe.provide("organizer_toolkit");

organizer_toolkit.rapid_block_entry = function(options) {
    options = options || {};

    const locality = (window.frappe && frappe.boot && frappe.boot.ot_locality) || {};
    const logged = [];

    const dialog = new frappe.ui.Dialog({
        title: __("Rapid Block Entry"),
        size: "small",
        fields: [
            // Whether doors count toward a walk list is invisible otherwise -- the
            // dialog looks identical either way, and the difference only shows up later
            // in that list's progress.
            ...(options.walk_list
                ? [
                      {
                          fieldname: "walk_list_html",
                          fieldtype: "HTML",
                          options: `<p class="text-muted small" style="margin-bottom:0">${__(
                              "Counting toward walk list {0}.",
                              [`<b>${frappe.utils.escape_html(options.walk_list)}</b>`]
                          )}</p>`,
                      },
                  ]
                : []),
            {
                fieldname: "block_sb",
                fieldtype: "Section Break",
                label: __("The block — entered once"),
            },
            {
                fieldname: "street",
                fieldtype: "Data",
                label: __("Street"),
                reqd: 1,
                default: options.street || "",
                description: __("Without the house number, e.g. S 52nd St"),
            },
            { fieldname: "block_cb", fieldtype: "Column Break" },
            {
                fieldname: "city",
                fieldtype: "Data",
                label: __("City"),
                default: options.city || locality.default_city || "",
            },
            {
                fieldname: "state",
                fieldtype: "Data",
                label: __("State"),
                default: options.state || locality.default_state || "",
            },
            { fieldname: "postal_code", fieldtype: "Data", label: __("Postal Code") },

            { fieldname: "door_sb", fieldtype: "Section Break", label: __("This door") },
            { fieldname: "house_number", fieldtype: "Data", label: __("House Number"), reqd: 1 },
            { fieldname: "door_cb", fieldtype: "Column Break" },
            {
                fieldname: "outcome",
                fieldtype: "Select",
                label: __("Outcome"),
                reqd: 1,
                options: "\nNo answer\nNot interested\nAbandoned\nAnswered",
            },
            { fieldname: "notes_sb", fieldtype: "Section Break" },
            { fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
            { fieldname: "logged_html", fieldtype: "HTML" },
        ],
        primary_action_label: __("Save & Next Door"),
        primary_action: () => save_door(),
    });

    function render_log() {
        const html = logged.length
            ? `<div class="text-muted small"><b>${logged.length}</b> ${__(
                  "door(s) logged"
              )}</div><ul class="small" style="padding-left:1rem;margin-bottom:0">${logged
                  .slice(-5)
                  .reverse()
                  .map((entry) => `<li>${frappe.utils.escape_html(entry)}</li>`)
                  .join("")}</ul>`
            : `<div class="text-muted small">${__("Nothing logged yet.")}</div>`;

        dialog.fields_dict.logged_html.$wrapper.html(html);
    }

    function save_door() {
        const values = dialog.get_values();
        if (!values) return;

        // Keep the block fields; only the per-door ones are cleared after a save.
        dialog.disable_primary_action();

        frappe.call({
            method: "organizer_toolkit.organizer_toolkit.doctype.ot_canvass_attempt.ot_canvass_attempt.log_visit",
            args: {
                address_line_1: `${values.house_number} ${values.street}`.trim(),
                city: values.city || null,
                state: values.state || null,
                postal_code: values.postal_code || null,
                outcome: values.outcome,
                notes: values.notes || null,
                walk_list: options.walk_list || null,
            },
            callback(r) {
                if (!r.message) return;

                logged.push(`${r.message.street_address} — ${values.outcome}`);
                render_log();

                // Clear only the door, then put the cursor back on the house number so
                // the next door is a number, an outcome and a tap.
                dialog.set_value("house_number", "");
                dialog.set_value("outcome", "");
                dialog.set_value("notes", "");

                const input = dialog.fields_dict.house_number.$input;
                if (input && input.length) input.focus();

                if (options.on_save) options.on_save(r.message);
            },
            always() {
                // Re-enable even on failure: a dropped request should be a retry, not a
                // dead dialog with the typed values stranded behind it.
                dialog.enable_primary_action();
            },
        });
    }

    dialog.set_secondary_action_label(__("Done"));
    dialog.set_secondary_action(() => dialog.hide());

    dialog.show();
    render_log();

    // Straight to the first house number when the block is already known.
    if (options.street) {
        const input = dialog.fields_dict.house_number.$input;
        if (input && input.length) input.focus();
    }

    return dialog;
};
