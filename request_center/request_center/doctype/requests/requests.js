// =============================================================================
// FORM EVENTS: Requests
// =============================================================================
frappe.ui.form.on('Requests', {

    // -------------------------------------------------------------------------
    // Refresh: buttons for viewing approvers / executing the request
    // -------------------------------------------------------------------------
    refresh: function (frm) {
        refresh_all_requirement_rows(frm);

        frm.add_custom_button(__('View Approvers'), function () {
            frappe.call({
                method: 'request_center.request_center.doctype.requests.requests.get_approvers',
                args: { request_name: frm.doc.name },
                callback: function (r) {
                    if (r.message) {
                        let html = '<h5>Approval Chain</h5>';

                        if (!Object.keys(r.message).length) {
                            html += '<p>No approvers found</p>';
                        } else {
                            html += `<table class="table table-bordered">
                                <thead><tr><th>Level</th><th>Approvers</th></tr></thead><tbody>`;

                            for (let level in r.message) {
                                html += `
                                    <tr>
                                        <td><b>Level ${level}</b></td>
                                        <td>${r.message[level].join('<br>')}</td>
                                    </tr>`;
                            }

                            html += '</tbody></table>';
                        }

                        frappe.msgprint(html);
                    }
                }
            });
        });

        if (frm.doc.status === "Approved") {
            frm.add_custom_button(__('Execute'), function () {
                frappe.confirm('Are you sure?', function () {
                    frappe.call({
                        method: 'request_center.request_center.doctype.requests.requests.execute_request',
                        args: { request_name: frm.doc.name },
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint(r.message.message);
                                frm.reload_doc();
                            }
                        }
                    });
                });
            });
        }
    },

    // -------------------------------------------------------------------------
    // Request Type change: rebuild the requirements table 
    // -------------------------------------------------------------------------
    request_type: function (frm) {
        if (!frm.doc.request_type) {
            frm.clear_table('requirements');
            frm.refresh_field('requirements');
            return;
        }

        // Remember what the user already typed in, keyed by field_key,
        // so switching (or re-triggering) request_type doesn't wipe it.
        const existing_values = {};
        (frm.doc.requirements || []).forEach(row => {
            if (row.field_key) {
                existing_values[row.field_key] = row.value;
            }
        });

        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Request Type', name: frm.doc.request_type },
            callback: function (r) {
                if (r.message && r.message.requirements) {
                    frm.clear_table('requirements');

                    r.message.requirements.forEach(src => {
                        let row = frm.add_child('requirements');
                        row.field_label = src.field_label;
                        row.field_key = src.field_key;
                        row.field_type = src.field_type;
                        row.field_options = src.field_options;
                        row.is_mandatory = src.mandatory;
                        row.sort_order = src.sort_order;

                        // Restore whatever the user had entered for this key before.
                        if (src.field_key in existing_values) {
                            row.value = existing_values[src.field_key];
                        }
                    });

                    frm.refresh_field('requirements');
                    refresh_all_requirement_rows(frm);
                }
            }
        });
    }
});


// =============================================================================
// CHILD TABLE EVENTS: Request Requirement Value
// =============================================================================
frappe.ui.form.on("Request Requirement Value", {

    // Re-render the Value widget whenever the field's type/options change
    field_type: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    field_options: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    form_render: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    requirements_add: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    // Client-side sanity check the moment the user leaves the Value cell,
    // so bad Link values get flagged immediately instead of only at save.
    value: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || row.field_type !== "Link" || !row.value || !row.field_options) return;

        frappe.db.exists(row.field_options, row.value).then(exists => {
            if (!exists) {
                frappe.show_alert({
                    message: __('"{0}" is not a valid {1}', [row.value, row.field_options]),
                    indicator: 'red'
                });
            }
        });
    }
});


// =============================================================================
// HELPERS
// =============================================================================

// Refresh all rows
function refresh_all_requirement_rows(frm) {
    if (!frm.fields_dict.requirements) return;

    setTimeout(() => {
        (frm.doc.requirements || []).forEach(row => {
            update_value_widget(frm, row.doctype, row.name);
        });
    }, 200);
}


// Dynamic field type switcher — makes the Value cell render as the correct
// widget (Link picker, Date picker, Check box, etc.) based on field_type.
function update_value_widget(frm, cdt, cdn) {

    const row = locals[cdt][cdn];
    if (!row) return;

    const grid = frm.fields_dict.requirements.grid;
    const grid_row = grid.grid_rows_by_docname[cdn];
    if (!grid_row) return;

    const df = grid_row.docfields.find(d => d.fieldname === "value");
    if (!df) return;

    switch (row.field_type) {

        case "Date":
            df.fieldtype = "Date";
            df.options = "";
            break;

        case "Datetime":
            df.fieldtype = "Datetime";
            break;

        case "Check":
            df.fieldtype = "Check";
            break;

        case "Int":
            df.fieldtype = "Int";
            break;

        case "Float":
            df.fieldtype = "Float";
            break;

        case "Currency":
            df.fieldtype = "Currency";
            break;

        case "Text":
            df.fieldtype = "Text";
            break;

        default:
            df.fieldtype = "Data";
    }

    grid_row.refresh_field("value");
}