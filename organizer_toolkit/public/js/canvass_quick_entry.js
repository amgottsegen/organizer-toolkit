// Field-entry tweaks for doorknocking.
//
// Quick Entry is the whole mobile UI for logging visits -- it never runs form scripts,
// so behaviour that has to reach it lives here, in a QuickEntryForm subclass. Frappe
// picks these up automatically by name: `frappe.ui.form.<DocTypeWithoutSpaces>QuickEntryForm`.

frappe.provide("frappe.ui.form");

// Remembers the block a canvasser is currently working so the unchanging parts of an
// address are not retyped at every door. Session-scoped on purpose: it should not
// survive into tomorrow's shift.
const OT_BLOCK_KEY = "ot_canvass_block_context";

function ot_read_block_context() {
    try {
        return JSON.parse(sessionStorage.getItem(OT_BLOCK_KEY)) || null;
    } catch (e) {
        return null;
    }
}

function ot_write_block_context(doc) {
    if (!doc || !doc.address_line_1) return;
    try {
        sessionStorage.setItem(
            OT_BLOCK_KEY,
            JSON.stringify({
                street: ot_street_without_number(doc.address_line_1),
                city: doc.city || "",
                state: doc.state || "",
                postal_code: doc.postal_code || "",
            })
        );
    } catch (e) {
        // Private browsing or a full quota -- prefill is a convenience, never a blocker.
    }
}

// "1423 S 52nd St" -> "S 52nd St". Only the house number changes door to door.
function ot_street_without_number(line) {
    const tokens = String(line).trim().split(/\s+/);
    return tokens.length > 1 && /^\d+[a-z]?$/i.test(tokens[0])
        ? tokens.slice(1).join(" ")
        : tokens.join(" ");
}

frappe.ui.form.OTAddressQuickEntryForm = class OTAddressQuickEntryForm extends frappe.ui.form
    .QuickEntryForm {
    constructor(...args) {
        super(...args);
        // On a failed save Frappe otherwise throws the user into the full form, losing
        // the fast path exactly when signal is worst. Staying in the dialog keeps the
        // typed values and re-enables Save, so a dropped request is a retry, not a loss.
        this.skip_redirect_on_error = true;
    }

    set_defaults() {
        super.set_defaults();
        this.apply_block_context();
        this.request_device_location();
    }

    // A canvasser filling this in is standing at the door, so the phone's own position
    // is both instant and usually better than a geocoder's rooftop guess. Requested as
    // the dialog opens so the fix has arrived by the time they hit Save -- which also
    // means OT Address.after_insert sees a location and skips queueing Nominatim.
    request_device_location() {
        this._device_fix = null;

        if (!navigator.geolocation) return;
        // Only when logging a door, not when editing an address from the desk.
        if (!cur_frm || !cur_frm.doc || cur_frm.doc.doctype !== "OT Canvass Attempt") return;

        navigator.geolocation.getCurrentPosition(
            (position) => {
                this._device_fix = {
                    lat: position.coords.latitude,
                    lon: position.coords.longitude,
                };
            },
            () => {
                // Denied, unavailable, or timed out -- the background geocoder covers it.
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    }

    // GeoJSON orders coordinates [longitude, latitude]; this mirrors
    // address_utils.build_location_geojson on the server.
    device_location_geojson() {
        if (!this._device_fix) return null;

        return JSON.stringify({
            type: "FeatureCollection",
            features: [
                {
                    type: "Feature",
                    geometry: {
                        type: "Point",
                        coordinates: [this._device_fix.lon, this._device_fix.lat],
                    },
                    properties: {},
                },
            ],
        });
    }

    apply_block_context() {
        const context = ot_read_block_context();
        if (!context) return;

        for (const fieldname of ["city", "state", "postal_code"]) {
            if (context[fieldname] && this.dialog.fields_dict[fieldname] && !this.dialog.doc[fieldname]) {
                this.dialog.set_value(fieldname, context[fieldname]);
            }
        }

        if (!context.street || !this.dialog.fields_dict.address_line_1) return;
        if (this.dialog.doc.address_line_1) return;

        // Prefill the street and park the caret in front of it, so the canvasser types
        // only the house number and moves on. Editing the street here is what switches
        // the remembered block -- the next save restashes it, so it self-corrects.
        this.dialog.set_value("address_line_1", context.street);

        const input = this.dialog.fields_dict.address_line_1.$input;
        if (input && input.length) {
            input.focus();
            try {
                input[0].setSelectionRange(0, 0);
            } catch (e) {
                // Some mobile keyboards reject caret positioning; harmless.
            }
        }
    }

    insert() {
        // Attach the fix before the round trip so the address is created already
        // located -- the server then has no reason to queue a geocoding job for it.
        const fix = this.device_location_geojson();
        if (fix && this.dialog.doc && !this.dialog.doc.location) {
            this.dialog.doc.location = fix;
        }

        return super.insert().then((doc) => {
            // `always` resolves this promise on failure too, so only remember the block
            // once the address genuinely saved.
            if (doc && doc.name && !doc.__islocal) {
                ot_write_block_context(doc);
            }
            return doc;
        });
    }
};

frappe.ui.form.OTConstituentQuickEntryForm = class OTConstituentQuickEntryForm extends frappe.ui
    .form.QuickEntryForm {
    constructor(...args) {
        super(...args);
        this.skip_redirect_on_error = true;
    }

    set_defaults() {
        super.set_defaults();

        // Opened from the constituent link on a canvass attempt: the door is already
        // known, so carry it across rather than making the canvasser pick it twice.
        const calling = cur_frm;
        if (
            calling &&
            calling.doc &&
            calling.doc.doctype === "OT Canvass Attempt" &&
            calling.doc.address &&
            this.dialog.fields_dict.address &&
            !this.dialog.doc.address
        ) {
            this.dialog.set_value("address", calling.doc.address);
        }
    }

    insert() {
        // The "Confirm New OT Constituent" Client Script guards against creating a
        // duplicate person, but Client Scripts never run inside a Quick Entry dialog --
        // so without this, entering someone from a door would skip the check entirely.
        if (this._duplicate_check_done) {
            return super.insert();
        }

        const values = this.dialog.get_values(true) || {};

        if (!values.address) {
            this._duplicate_check_done = true;
            return super.insert();
        }

        const quick_entry = this;

        return frappe
            .call({
                method: "organizer_toolkit.api.compare_against_name_and_address",
                args: {
                    first_name: values.first_name || "",
                    last_name: values.last_name || "",
                    address: values.address,
                },
            })
            .then((r) => {
                const matches = r.message || [];

                if (!matches.length) {
                    quick_entry._duplicate_check_done = true;
                    return super.insert();
                }

                quick_entry.dialog.working = false;
                quick_entry.dialog.clear_message();
                quick_entry.show_possible_duplicates(matches);
            });
    }

    show_possible_duplicates(matches) {
        const quick_entry = this;
        const rows = matches
            .map(
                (c) =>
                    `<li><a href="/app/ot-constituent/${c.name}" target="_blank">
                        ${frappe.utils.escape_html(
                            [c.first_name, c.last_name].filter(Boolean).join(" ") || c.name
                        )}</a>
                     &mdash; ${frappe.utils.escape_html(c.street_address || "")}</li>`
            )
            .join("");

        const confirm = new frappe.ui.Dialog({
            title: __("Possible duplicate"),
            fields: [
                {
                    fieldtype: "HTML",
                    options: `<p>${__(
                        "Someone similar is already recorded at this address:"
                    )}</p><ul>${rows}</ul><p>${__(
                        "Open one of them instead, or continue to create a new person."
                    )}</p>`,
                },
            ],
            primary_action_label: __("Create anyway"),
            primary_action() {
                confirm.hide();
                quick_entry._duplicate_check_done = true;
                quick_entry.dialog.get_primary_btn().trigger("click");
            },
            secondary_action_label: __("Cancel"),
            secondary_action() {
                confirm.hide();
            },
        });

        confirm.show();
    }
};

frappe.ui.form.OTCanvassAttemptQuickEntryForm = class OTCanvassAttemptQuickEntryForm extends frappe
    .ui.form.QuickEntryForm {
    constructor(...args) {
        super(...args);
        this.skip_redirect_on_error = true;
    }

    set_meta_and_mandatory_fields() {
        super.set_meta_and_mandatory_fields();

        // Recording who you spoke to means somebody answered the door. The form script
        // handles this on the full form, but Quick Entry builds its dialog straight from
        // meta and never runs form scripts -- so the same rule is wired onto the field
        // here. `onchange` on the field definition is honoured by dialog controls.
        const constituent = (this.mandatory || []).find(df => df.fieldname === "constituent");
        if (!constituent) return;

        const quick_entry = this;
        constituent.onchange = function () {
            const dialog = quick_entry.dialog;
            if (!dialog) return;
            // Fill only when blank so an explicit "Not interested" survives.
            if (dialog.get_value("constituent") && !dialog.get_value("outcome")) {
                dialog.set_value("outcome", "Answered");
            }
        };
    }
};
