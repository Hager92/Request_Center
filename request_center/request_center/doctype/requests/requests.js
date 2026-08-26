// =============================================================================
// FORM EVENTS: Requests
// =============================================================================
frappe.ui.form.on('Requests', {

    onload: function (frm) {
        frm.set_query("request_type", function () {
            return { filters: { is_active: 1 } };
        });

        if (frm.is_new()) {
            if (!frm.doc.requested_by || frm.doc.requested_by === "user") {
                frm.set_value("requested_by", frappe.session.user);
            }
            if (!frm.doc.request_date) {
                frm.set_value("request_date", frappe.datetime.now_datetime());
            }
            if (!frm.doc.status) {
                frm.set_value("status", "Draft");
            }
        }

        if (frm.is_new() && frm.doc.request_type) {
            frappe.db.get_value("Request Type", frm.doc.request_type, "is_active").then((r) => {
                const active = r && r.message && r.message.is_active;
                if (!cint(active)) {
                    frappe.msgprint(
                        __("Request Type {0} is inactive and cannot be used for new requests", [
                            frm.doc.request_type,
                        ])
                    );
                    frm.set_value("request_type", "");
                    return;
                }
                frm.trigger("request_type");
            });
        }
    },

    after_workflow_action: function (frm) {
        frm.reload_doc();
    },

    // -------------------------------------------------------------------------
    // Refresh: buttons for viewing approvers / executing the request
    // -------------------------------------------------------------------------
    refresh: function (frm) {
        frm.set_df_property("status", "read_only", 1);
        frm.set_df_property("requested_by", "read_only", 1);
        frm.set_df_property("request_date", "read_only", 1);
        frm.set_df_property("department", "read_only", 1);
        frm.set_df_property("current_approval_level", "read_only", 1);
        frm.set_df_property("current_approver", "read_only", 1);

        if (frm.is_new() && frm.doc.request_type) {
            frm.set_df_property("request_type", "read_only", 1);
        } else if (frm.is_new()) {
            frm.set_df_property("request_type", "read_only", 0);
        }

        if (frm.fields_dict.requirements && frm.fields_dict.requirements.grid) {
            frm.fields_dict.requirements.grid.cannot_add_rows = true;
            frm.fields_dict.requirements.grid.cannot_delete_rows = true;
        }

        refresh_all_requirement_rows(frm);
        lock_approval_tracking_grid(frm);
        toggle_material_items(frm);
        pull_tender_suppliers(frm);
        render_request_experience(frm);
        show_approval_status(frm);
        add_approval_actions(frm);
        add_fulfillment_links(frm);
        add_material_workflow_actions(frm);
        add_supplier_comparison_button(frm);

        frm.add_custom_button(__("Request Center"), function () {
            frappe.set_route("request-center-home");
        });

        frm.add_custom_button(__('View Approvers'), function () {
            show_approval_tracking_dialog(frm);
        });

        if (frm.doc.status === "Approved" && frm.doc.category !== "Material Request") {
            frm.add_custom_button(__("Start Service / Other Process"), function () {
                frappe.confirm(__("Start the Service / Other Process for this request?"), function () {
                    frappe.call({
                        method: 'request_center.api.requests.execute_request',
                        args: { request_name: frm.doc.name },
                        freeze: true,
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
    // Validate: block save client-side if any mandatory requirement is empty
    // -------------------------------------------------------------------------
    validate: function (frm) {
        if (frm.doc.status && frm.doc.status !== "Draft") {
            assert_mandatory_fields(frm);
        }

        if (frm.doc.category === "Material Request" && frm.doc.status && frm.doc.status !== "Draft") {
            const items = (frm.doc.material_items || []).filter((row) => row.item_code && flt(row.qty) > 0);
            if (!items.length) {
                frappe.throw(__("Add at least one item with quantity for a Material Request"));
            }
        }
    },

    before_workflow_action: function (frm) {
        try {
            if (frm.selected_workflow_action === "Submit") {
                assert_mandatory_fields(frm);
            }
            if (frm.doc.category !== "Material Request") {
                return;
            }
            const items = (frm.doc.material_items || []).filter((row) => row.item_code && flt(row.qty) > 0);
            if (!items.length) {
                frappe.throw(__("Add at least one item with quantity for a Material Request"));
            }
        } catch (e) {
            frappe.dom.unfreeze();
            throw e;
        }
    },

    // -------------------------------------------------------------------------
    // Request Type change: rebuild the requirements table 
    // -------------------------------------------------------------------------
    request_type: function (frm) {
        if (!frm.doc.request_type) {
            frm.clear_table('requirements');
            frm.refresh_field('requirements');
            frm.set_value("current_approver", "");
            frm.set_value("current_approval_level", "");
            if (frm.fields_dict.current_approver_user) {
                frm.set_value("current_approver_user", "");
            }
            if (frm.fields_dict.approval_status_summary) {
                frm.set_value("approval_status_summary", "");
            }
            if (frm.fields_dict.approval_tracking) {
                frm.clear_table("approval_tracking");
                frm.refresh_field("approval_tracking");
            }
            show_approval_status(frm);
            toggle_material_items(frm);
            render_request_experience(frm);
            return;
        }

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
            if (r.message) {
                    frm.clear_table('requirements');

                    (r.message.requirements || []).forEach(src => {
                        let row = frm.add_child('requirements');
                        row.field_label = src.field_label;
                        row.field_key = src.field_key;
                        row.field_type = src.field_type;
                        row.options = src.options;
                        row.is_mandatory = src.mandatory;
                        row.sort_order = src.sort_order;

                        if (src.field_key in existing_values) {
                            row.value = existing_values[src.field_key];
                        }
                    });

                    frm.refresh_field('requirements');
                    refresh_all_requirement_rows(frm);
                    refresh_approval_tracking_preview(frm);
                    if (r.message.category) {
                        frm.set_value("category", r.message.category);
                    }
                    toggle_material_items(frm);
                    render_request_experience(frm);
                }
            }
        });
    }
});


// =============================================================================
// CHILD TABLE EVENTS: Request Requirement Value
// =============================================================================
frappe.ui.form.on("Request Requirement Value", {

    field_type: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    options: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    form_render: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    },

    requirements_add: function (frm, cdt, cdn) {
        update_value_widget(frm, cdt, cdn);
    }
});


// =============================================================================
// HELPERS
// =============================================================================

function assert_mandatory_fields(frm) {
    const missing = [];
    (frm.doc.requirements || []).forEach((row) => {
        if (cint(row.is_mandatory) && !row.value) {
            missing.push(row.field_label || row.field_key || "Unknown Field");
        }
    });
    if (missing.length) {
        frappe.throw(
            __("Please fill a value for mandatory field(s): {0}", [missing.join(", ")])
        );
    }
}

function lock_approval_tracking_grid(frm) {
    if (!(frm.fields_dict.approval_tracking && frm.fields_dict.approval_tracking.grid)) {
        return;
    }
    frm.fields_dict.approval_tracking.grid.cannot_add_rows = true;
    frm.fields_dict.approval_tracking.grid.cannot_delete_rows = true;
}


function toggle_material_items(frm) {
    const is_material = frm.doc.category === "Material Request";
    frm.toggle_display("section_break_material", is_material);
    frm.toggle_display("material_items", is_material);
    frm.toggle_display("fulfillment_path", !!frm.doc.fulfillment_path);
    frm.toggle_display("inventory_check_result", is_material && !!frm.doc.inventory_check_result);
    frm.toggle_display("fulfillment_stage", !!frm.doc.fulfillment_stage);
    frm.toggle_display("section_break_material_workflow", is_material);
    frm.toggle_display("material_workflow", is_material);
    frm.toggle_display("linked_documents", is_material);
    frm.toggle_display("material_suppliers", is_material);
    frm.toggle_display("tender", is_material && !!frm.doc.tender);
    frm.toggle_display("rfq", is_material && !!frm.doc.rfq);
    frm.toggle_display("purchase_order", is_material && !!frm.doc.purchase_order);
    frm.toggle_display("tender_reference", is_material);
    frm.toggle_display("tender_notes", is_material);
    frm.toggle_display("supplier_comparison", is_material);
    frm.toggle_display("comparison_method", is_material && !!frm.doc.comparison_method);
    frm.toggle_display("recommended_quotation", is_material && !!frm.doc.recommended_quotation);
    frm.toggle_display("selected_quotation", is_material);
    frm.toggle_display("awarded_supplier", is_material);
    frm.toggle_display("expected_delivery_date", is_material);
    frm.toggle_display("comparison_notes", is_material);

    if (frm.fields_dict.material_workflow && frm.fields_dict.material_workflow.grid) {
        frm.fields_dict.material_workflow.grid.cannot_add_rows = true;
        frm.fields_dict.material_workflow.grid.cannot_delete_rows = true;
    }
    if (frm.fields_dict.linked_documents && frm.fields_dict.linked_documents.grid) {
        frm.fields_dict.linked_documents.grid.cannot_add_rows = true;
        frm.fields_dict.linked_documents.grid.cannot_delete_rows = true;
    }
    if (frm.fields_dict.supplier_comparison && frm.fields_dict.supplier_comparison.grid) {
        frm.fields_dict.supplier_comparison.grid.cannot_add_rows = true;
        frm.fields_dict.supplier_comparison.grid.cannot_delete_rows = true;
    }

    if (frm.fields_dict.material_suppliers && frm.fields_dict.material_suppliers.grid) {
        frm.fields_dict.material_suppliers.grid.cannot_add_rows = true;
        frm.fields_dict.material_suppliers.grid.cannot_delete_rows = true;
        frm.set_df_property("material_suppliers", "read_only", 1);
    }
    frm.set_df_property("tender", "read_only", 1);
    frm.set_df_property("rfq", "read_only", 1);
    frm.set_df_property("purchase_order", "read_only", 1);
    frm.set_df_property("tender_notes", "read_only", frm.doc.fulfillment_stage === "Tender" ? 0 : 1);
    frm.set_df_property("tender_reference", "read_only", frm.doc.fulfillment_stage === "Tender" ? 0 : 1);
    frm.set_df_property("selected_quotation", "read_only", frm.doc.fulfillment_stage === "Supplier Comparison" ? 0 : 1);
    frm.set_df_property("expected_delivery_date", "read_only", frm.doc.fulfillment_stage === "Supplier Comparison" ? 0 : 1);
    frm.set_df_property("comparison_notes", "read_only", frm.doc.fulfillment_stage === "Supplier Comparison" ? 0 : 1);

    if (!(frm.fields_dict.material_items && frm.fields_dict.material_items.grid)) {
        return;
    }
    const locked = !["Draft", "", null, undefined].includes(frm.doc.status);
    frm.fields_dict.material_items.grid.cannot_add_rows = locked;
    frm.fields_dict.material_items.grid.cannot_delete_rows = locked;
    frm.set_df_property("material_items", "read_only", locked ? 1 : 0);
}


function pull_tender_suppliers(frm) {
    if (frm.is_new() || !frm.doc.tender) {
        return;
    }
    frappe.call({
        method: "request_center.tender.sync_request_suppliers",
        args: { tender_name: frm.doc.tender },
        callback: function (r) {
            if (r.message && r.message.copied) {
                frm.reload_doc();
            }
        },
    });
}


function add_fulfillment_links(frm) {
    const names = [];
    if (frm.doc.tender) {
        names.push({ doctype: "Tender", name: frm.doc.tender });
        frm.add_custom_button(__("Open Tender"), function () {
            frappe.set_route("Form", "Tender", frm.doc.tender);
        }).addClass("btn-primary");
    }
    if (frm.doc.rfq) {
        names.push({ doctype: "Request for Quotation", name: frm.doc.rfq });
        frm.add_custom_button(__("Open RFQ"), function () {
            frappe.set_route("Form", "Request for Quotation", frm.doc.rfq);
        }).addClass("btn-primary");
    }
    if (frm.doc.purchase_order) {
        names.push({ doctype: "Purchase Order", name: frm.doc.purchase_order });
        frm.add_custom_button(__("Open Purchase Order"), function () {
            frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order);
        }).addClass("btn-primary");
    }
    (frm.doc.linked_documents || []).forEach(function (row) {
        if (row.document_type && row.document_name) {
            names.push({ doctype: row.document_type, name: row.document_name });
        }
    });
    if (frm.doc.execution_doctype && frm.doc.execution_docname) {
        String(frm.doc.execution_docname).split(",").forEach(function (name) {
            name = (name || "").trim();
            if (name) {
                names.push({ doctype: frm.doc.execution_doctype, name: name });
            }
        });
    }
    (frm.doc.material_workflow || []).forEach(function (row) {
        if (row.document_type && row.document_name) {
            String(row.document_name).split(",").forEach(function (name) {
                name = (name || "").trim();
                if (name) {
                    names.push({ doctype: row.document_type, name: name });
                }
            });
        }
    });
    const seen = {};
    names.forEach(function (row) {
        const key = row.doctype + "::" + row.name;
        if (seen[key]) {
            return;
        }
        seen[key] = true;
        frm.add_custom_button(row.name, function () {
            frappe.set_route("Form", row.doctype, row.name);
        }, __("Fulfillment"));
    });
}


function add_material_workflow_actions(frm) {
    if (frm.is_new() || frm.doc.category !== "Material Request") {
        return;
    }
    if (!["Approved", "In Progress"].includes(frm.doc.status)) {
        return;
    }
    frappe.call({
        method: "request_center.material_workflow.get_material_workflow_action",
        args: { request_name: frm.doc.name },
        callback: function (r) {
            const data = r.message || {};
            if (!data.can_act) {
                return;
            }
            (data.stages || []).forEach(function (step) {
                frm.add_custom_button(step.label, function () {
                    run_material_workflow_step(frm, step);
                }).addClass("btn-primary");
            });
        },
    });
}


function run_material_workflow_step(frm, step) {
    const go = function (values) {
        frappe.call({
            method: "request_center.material_workflow.advance_material_workflow",
            args: {
                request_name: frm.doc.name,
                stage: step.stage,
                tender_notes: values.tender_notes || frm.doc.tender_notes,
                tender_reference: values.tender_reference || frm.doc.tender_reference,
                selected_quotation: values.selected_quotation || frm.doc.selected_quotation,
                expected_delivery_date: values.expected_delivery_date || frm.doc.expected_delivery_date,
                comparison_notes: values.comparison_notes || frm.doc.comparison_notes,
            },
            freeze: true,
            callback: function (res) {
                if (res.message) {
                    frappe.msgprint(res.message.message);
                    frm.reload_doc();
                }
            },
        });
    };

    if (step.stage === "Supplier Selection") {
        go({});
        return;
    }

    if (step.stage === "RFQ") {
        const suppliers = (frm.doc.material_suppliers || [])
            .map(function (row) {
                return row.supplier;
            })
            .filter(Boolean);
        const names = suppliers.length ? suppliers.join(", ") : __("the suppliers selected on the Tender");
        frappe.confirm(
            __("Create and send RFQ to {0}? Suppliers will provide offers for comparison.", [names]),
            function () {
                go({});
            }
        );
        return;
    }

    if (step.stage === "PO") {
        const supplier = frm.doc.awarded_supplier || __("the selected supplier");
        frappe.confirm(
            __("Create a Purchase Order for {0}? It will stay linked to this requisition, the Material Request, the Tender, and the supplier.", [
                supplier,
            ]),
            function () {
                go({});
            }
        );
        return;
    }

    if (step.prompt === "tender") {
        frappe.prompt(
            [
                {
                    fieldname: "tender_reference",
                    fieldtype: "Data",
                    label: __("Tender Reference"),
                    default: frm.doc.tender_reference || "",
                },
                {
                    fieldname: "tender_notes",
                    fieldtype: "Small Text",
                    label: __("Tender Notes"),
                    default: frm.doc.tender_notes || "",
                },
            ],
            function (values) {
                go(values);
            },
            __("Tender"),
            __("Complete Tender")
        );
        return;
    }

    if (step.prompt === "comparison") {
        prompt_supplier_comparison(frm, step, go);
        return;
    }

    if (step.prompt === "price_delivery") {
        const fields = [
            {
                fieldname: "selected_quotation",
                fieldtype: "Link",
                options: "Supplier Quotation",
                label: __("Selected Supplier Quotation"),
                default: frm.doc.selected_quotation || "",
            },
            {
                fieldname: "expected_delivery_date",
                fieldtype: "Date",
                label: __("Expected Delivery Date"),
                default: frm.doc.expected_delivery_date || "",
            },
        ];
        frappe.prompt(
            fields,
            function (values) {
                go(values);
            },
            __(step.label),
            __("Continue")
        );
        return;
    }

    frappe.confirm(__("Advance to {0}?", [step.label]), function () {
        go({});
    });
}


function add_supplier_comparison_button(frm) {
    if (frm.is_new() || frm.doc.category !== "Material Request") {
        return;
    }
    const has_rows = (frm.doc.supplier_comparison || []).length;
    const at_comparison = ["Supplier Comparison", "Price + Delivery", "PO", "Delivery", "Completed"].includes(
        frm.doc.fulfillment_stage
    );
    if (!has_rows && !at_comparison) {
        return;
    }
    frm.add_custom_button(__("View Supplier Comparison"), function () {
        prompt_supplier_comparison(frm, { label: __("Supplier Comparison") });
    });
}


function prompt_supplier_comparison(frm, step, go) {
    frappe.call({
        method: "request_center.supplier_comparison.get_supplier_comparison",
        args: { request_name: frm.doc.name },
        freeze: true,
        callback: function (r) {
            const data = (r && r.message) || {};
            const rows = data.rows || [];
            if (!rows.length) {
                frappe.msgprint(
                    __("Submit at least one Supplier Quotation against the RFQ, then compare Price and Delivery Time.")
                );
                return;
            }
            const labels = {};
            const options = rows.map(function (row) {
                const label = [row.supplier_name || row.supplier, row.price_display, row.delivery_time]
                    .filter(Boolean)
                    .join(" — ");
                labels[label] = row.supplier_quotation;
                return label;
            });
            const current_name = frm.doc.selected_quotation || data.recommended_quotation || rows[0].supplier_quotation;
            const current_label =
                options.find(function (label) {
                    return labels[label] === current_name;
                }) || options[0];
            const recommended_row = rows.find((row) => row.recommended) || rows[0];
            const fields = [
                {
                    fieldname: "comparison_html",
                    fieldtype: "HTML",
                    options: supplier_comparison_html(data),
                },
            ];
            if (go) {
                fields.push({
                    fieldname: "selected_offer",
                    fieldtype: "Select",
                    label: __("Select Supplier"),
                    options: options.join("\n"),
                    default: current_label,
                    reqd: 1,
                    description: __(
                        "Review Price and Delivery Time, then select the supplier according to purchasing policy."
                    ),
                });
                fields.push({
                    fieldname: "expected_delivery_date",
                    fieldtype: "Date",
                    label: __("Expected Delivery Date"),
                    default: frm.doc.expected_delivery_date || recommended_row.delivery_date || "",
                });
                fields.push({
                    fieldname: "comparison_notes",
                    fieldtype: "Small Text",
                    label: __("Selection Notes"),
                    default: frm.doc.comparison_notes || "",
                });
            }
            const dialog = new frappe.ui.Dialog({
                title: __(step.label || "Supplier Comparison"),
                size: "large",
                fields: fields,
                primary_action_label: go ? __("Select Supplier") : __("Close"),
                primary_action(values) {
                    if (go) {
                        go({
                            selected_quotation: labels[values.selected_offer] || values.selected_offer,
                            expected_delivery_date: values.expected_delivery_date,
                            comparison_notes: values.comparison_notes,
                        });
                    }
                    dialog.hide();
                },
            });
            dialog.show();
        },
    });
}


function supplier_comparison_html(data) {
    const rows = data.rows || [];
    const body = rows
        .map(function (row) {
            const rank = row.recommended
                ? "<strong>" + frappe.utils.escape_html(String(row.rank)) + " ★</strong>"
                : frappe.utils.escape_html(String(row.rank || ""));
            const score = row.total_score != null ? flt(row.total_score).toFixed(2) : "";
            const highlight = row.recommended ? ' style="background-color: var(--bg-green, #eaf7ee);"' : "";
            const supplier_cell =
                frappe.utils.escape_html(row.supplier_name || row.supplier || "") +
                (row.recommended
                    ? ' <span class="indicator-pill green">' + __("Recommended") + "</span>"
                    : "");
            return (
                "<tr" +
                highlight +
                ">" +
                "<td>" +
                rank +
                "</td>" +
                "<td>" +
                supplier_cell +
                "</td>" +
                "<td>" +
                frappe.utils.escape_html(row.price_display || String(row.price || "")) +
                "</td>" +
                "<td>" +
                frappe.utils.escape_html(row.delivery_time || "") +
                "</td>" +
                "<td>" +
                frappe.utils.escape_html(score) +
                "</td>" +
                "</tr>"
            );
        })
        .join("");
    const summary = frappe.utils.escape_html(data.policy_summary || "");
    return (
        '<p class="text-muted">' +
        summary +
        "</p>" +
        '<table class="table table-bordered table-sm" style="margin-bottom: 0;">' +
        "<thead><tr>" +
        "<th>" +
        __("Rank") +
        "</th>" +
        "<th>" +
        __("Supplier") +
        "</th>" +
        "<th>" +
        __("Price") +
        "</th>" +
        "<th>" +
        __("Delivery Time") +
        "</th>" +
        "<th>" +
        __("Score") +
        "</th>" +
        "</tr></thead><tbody>" +
        body +
        "</tbody></table>"
    );
}


function render_request_experience(frm) {
    const $layout = $(frm.layout.wrapper).find(".form-layout").first();
    if (!$layout.length) {
        return;
    }
    let $host = $layout.children(".request-ux-wrap");
    if (!$host.length) {
        $host = $('<div class="request-ux-wrap"></div>');
        $layout.prepend($host);
    }
    if (frm.is_new()) {
        $host.html(architecture_pipeline_html(frm.doc));
        return;
    }

    const result = request_final_result(frm.doc);
    $host.html(`
        <div class="request-ux-tracker">
            <div class="request-ux-tracker__item">
                <span class="request-ux-tracker__label">${__("Request Status")}</span>
                <span class="request-ux-tracker__value">${frappe.utils.escape_html(frm.doc.status || "—")}</span>
            </div>
            <div class="request-ux-tracker__item">
                <span class="request-ux-tracker__label">${__("Current Approval Level")}</span>
                <span class="request-ux-tracker__value">${frappe.utils.escape_html(frm.doc.current_approval_level || "—")}</span>
            </div>
            <div class="request-ux-tracker__item">
                <span class="request-ux-tracker__label">${__("Current Approver")}</span>
                <span class="request-ux-tracker__value">${frappe.utils.escape_html(frm.doc.current_approver || "—")}</span>
            </div>
            <div class="request-ux-tracker__item">
                <span class="request-ux-tracker__label">${__("Final Result")}</span>
                <span class="request-ux-tracker__value">${frappe.utils.escape_html(result)}</span>
            </div>
        </div>
        ${architecture_pipeline_html(frm.doc)}
    `);
}

function request_final_result(doc) {
    if (doc.status === "Rejected") {
        return __("Rejected");
    }
    if (doc.status === "Completed") {
        return __("Completed");
    }
    if (doc.status === "Approved") {
        return __("Approved");
    }
    if (doc.status === "In Progress") {
        return doc.fulfillment_stage || __("In Progress");
    }
    if (
        ["Need Approval", "Pending Approval", "Pending Manager", "Pending Department"].includes(doc.status)
    ) {
        return __("Pending");
    }
    if (doc.status === "Draft") {
        return __("Draft");
    }
    return doc.status || "—";
}

function architecture_pipeline_html(doc) {
    if (doc.category === "Material Request") {
        return material_pipeline_html(doc);
    }
    return service_pipeline_html(doc);
}

function pipeline_pills(steps) {
    return `<div class="request-ux-pipeline">${steps
        .map((step) => {
            const cls = {
                Current: "is-current",
                Done: "is-done",
                Skipped: "is-skipped",
                Rejected: "is-rejected",
            }[step.status] || "";
            return `<span class="request-ux-pipeline__step ${cls}">${frappe.utils.escape_html(step.label)}</span>`;
        })
        .join("")}</div>`;
}

function approval_step_status(doc) {
    if (doc.status === "Rejected") {
        return "Rejected";
    }
    if (["Approved", "In Progress", "Completed"].includes(doc.status)) {
        return "Done";
    }
    if (
        ["Need Approval", "Pending Approval", "Pending Manager", "Pending Department"].includes(doc.status)
    ) {
        return "Current";
    }
    return "Pending";
}

function service_pipeline_html(doc) {
    let service = "Pending";
    if (doc.status === "Approved") {
        service = "Current";
    } else if (doc.status === "In Progress") {
        service = "Current";
    } else if (doc.status === "Completed") {
        service = "Done";
    } else if (doc.status === "Rejected") {
        service = "Pending";
    }
    return pipeline_pills([
        { label: __("Submit"), status: doc.status === "Draft" ? "Current" : "Done" },
        { label: __("Approval Levels"), status: approval_step_status(doc) },
        { label: __("Service / Other Process"), status: service },
        { label: __("Completed"), status: doc.status === "Completed" ? "Done" : "Pending" },
    ]);
}

function material_pipeline_html(doc) {
    const by_stage = {};
    (doc.material_workflow || []).forEach((row) => {
        by_stage[row.stage] = row.step_status;
    });
    const comparison =
        by_stage["Price + Delivery"] === "Current" || by_stage["Supplier Comparison"] === "Current"
            ? "Current"
            : by_stage["Price + Delivery"] === "Done" || by_stage["Supplier Comparison"] === "Done"
                ? "Done"
                : by_stage["Price + Delivery"] === "Skipped" && by_stage["Supplier Comparison"] === "Skipped"
                    ? "Skipped"
                    : by_stage["Supplier Comparison"] || by_stage["Price + Delivery"] || "Pending";

    return pipeline_pills([
        { label: __("Submit"), status: doc.status === "Draft" ? "Current" : "Done" },
        { label: __("Approval Levels"), status: approval_step_status(doc) },
        { label: __("Inventory Check"), status: by_stage["Inventory Check"] || "Pending" },
        {
            label: __("Transfer"),
            status: by_stage["Internal Transfer / Issuance"] || "Pending",
        },
        { label: __("Purchase"), status: by_stage["Purchase"] || by_stage["Supplier Selection"] || "Pending" },
        { label: __("Tender"), status: by_stage["Tender"] || "Pending" },
        { label: __("RFQ"), status: by_stage["RFQ"] || "Pending" },
        { label: __("Price + Delivery Comparison"), status: comparison },
        { label: __("PO"), status: by_stage["PO"] || "Pending" },
        { label: __("Delivery"), status: by_stage["Delivery"] || "Pending" },
        { label: __("Completed"), status: by_stage["Completed"] || (doc.status === "Completed" ? "Done" : "Pending") },
    ]);
}

function show_approval_status(frm) {
    frm.set_intro("");
    if (frm.is_new()) {
        frm.set_intro(
            __("Complete the form, then Submit. Approval Levels from the selected Request Type start after submission."),
            "blue"
        );
        return;
    }
    const parts = [];
    if (frm.doc.approval_status_summary) {
        parts.push(frappe.utils.escape_html(frm.doc.approval_status_summary));
    }
    if (frm.doc.category === "Material Request" && frm.doc.inventory_check_result) {
        const result_text = {
            Available: __("Inventory Check: material is available. The request is proceeding to Internal Transfer / Issuance."),
            "Not Available": __("Inventory Check: material is not available. The request is proceeding to the Purchase Process."),
            "Partially Available": __("Inventory Check: some material is available. Available quantity proceeds to Internal Transfer / Issuance; the rest proceeds to Purchase."),
        }[frm.doc.inventory_check_result];
        if (result_text) {
            parts.push(frappe.utils.escape_html(result_text));
        }
    }
    if (frm.doc.category === "Material Request" && (frm.doc.supplier_comparison || []).length) {
        const selected = (frm.doc.supplier_comparison || []).find((row) => cint(row.selected));
        if (selected) {
            parts.push(
                frappe.utils.escape_html(
                    __("Supplier Comparison: {0} selected at {1} / {2}.", [
                        selected.supplier_name || selected.supplier,
                        format_currency(selected.price, selected.currency),
                        selected.delivery_time || "",
                    ])
                )
            );
        } else {
            parts.push(
                frappe.utils.escape_html(
                    __("Supplier Comparison lists Price and Delivery Time for each offer. Review the table before selecting a supplier.")
                )
            );
        }
    }
    if (frm.doc.category === "Material Request" && frm.doc.rfq && !(frm.doc.supplier_comparison || []).length) {
        parts.push(
            frappe.utils.escape_html(
                __("RFQ {0} was sent to the selected suppliers. Enter or wait for their offers, then compare Price and Delivery Time.", [
                    frm.doc.rfq,
                ])
            )
        );
    }
    if (frm.doc.category === "Material Request" && frm.doc.purchase_order) {
        parts.push(
            frappe.utils.escape_html(
                __("Purchase Order {0} is linked to this requisition, the Material Request, the Tender, and supplier {1}.", [
                    frm.doc.purchase_order,
                    frm.doc.awarded_supplier || "",
                ])
            )
        );
    }
    if (!parts.length) {
        return;
    }
    const color = {
        Draft: "blue",
        "Need Approval": "orange",
        "Pending Approval": "orange",
        "Pending Manager": "orange",
        "Pending Department": "orange",
        Approved: "green",
        Rejected: "red",
        Completed: "blue",
        "In Progress": "yellow",
    }[frm.doc.status] || "blue";
    frm.set_intro(parts.join("<br>"), color);
}


function approval_tracking_table_html(rows) {
    if (!rows || !rows.length) {
        return `<p>${__("No approval levels configured")}</p>`;
    }
    let html = `<table class="table table-bordered">
        <thead><tr>
            <th>${__("Level")}</th>
            <th>${__("Approver")}</th>
            <th>${__("Status")}</th>
        </tr></thead><tbody>`;
    rows.forEach((row) => {
        html += `<tr>
            <td>${frappe.utils.escape_html(String(row.level || ""))}</td>
            <td>${frappe.utils.escape_html(row.approver || "")}</td>
            <td>${frappe.utils.escape_html(row.step_status || "")}</td>
        </tr>`;
    });
    html += "</tbody></table>";
    return html;
}


function show_approval_tracking_dialog(frm) {
    const open = (summary, rows) => {
        frappe.msgprint({
            title: __("Approval Tracking"),
            message: `<p><b>${frappe.utils.escape_html(summary || frm.doc.status || "")}</b></p>${approval_tracking_table_html(rows)}`,
        });
    };

    if (!frm.is_new() && (frm.doc.approval_tracking || []).length) {
        open(frm.doc.approval_status_summary, frm.doc.approval_tracking);
        return;
    }

    frappe.call({
        method: "request_center.api.requests.get_approval_tracking_preview",
        args: {
            request_type: frm.doc.request_type,
            department: frm.doc.department,
            status: frm.doc.status,
        },
        callback: function (r) {
            const data = r.message || {};
            open(data.approval_status_summary, data.rows || []);
        },
    });
}


function refresh_approval_tracking_preview(frm) {
    if (!frm.doc.request_type) {
        return;
    }
    frappe.call({
        method: "request_center.api.requests.get_approval_tracking_preview",
        args: {
            request_type: frm.doc.request_type,
            department: frm.doc.department,
            status: frm.doc.status || "Draft",
        },
        callback: function (r) {
            if (!r.message) {
                return;
            }
            const data = r.message;
            if (frm.doc.current_approver !== (data.current_approver || "")) {
                frm.set_value("current_approver", data.current_approver || "");
            }
            if (frm.doc.current_approval_level !== (data.current_approval_level || "")) {
                frm.set_value("current_approval_level", data.current_approval_level || "");
            }
            if (frm.fields_dict.approval_status_summary) {
                frm.set_value("approval_status_summary", data.approval_status_summary || "");
            }
            if (frm.fields_dict.approval_tracking) {
                frm.clear_table("approval_tracking");
                (data.rows || []).forEach((src) => {
                    const row = frm.add_child("approval_tracking");
                    row.level = src.level;
                    row.approver = src.approver;
                    row.step_status = src.step_status;
                });
                frm.refresh_field("approval_tracking");
                lock_approval_tracking_grid(frm);
            }
            show_approval_status(frm);
            render_request_experience(frm);
        },
    });
}


function add_approval_actions(frm) {
    if (frm.is_new() || !frm.doc.name) {
        return;
    }
    const pending = ["Need Approval", "Pending Approval", "Pending Manager", "Pending Department"];
    if (!pending.includes(frm.doc.status)) {
        return;
    }

    frappe.call({
        method: "request_center.api.requests.get_approval_action",
        args: { request_name: frm.doc.name },
        callback: function (r) {
            if (!(r.message && r.message.can_act)) {
                return;
            }
            frm.add_custom_button(__("Approve"), function () {
                frappe.call({
                    method: "request_center.api.requests.approve_request",
                    args: { request_name: frm.doc.name },
                    freeze: true,
                    callback: function (res) {
                        if (res.message) {
                            frappe.show_alert({ message: res.message.message, indicator: "green" });
                            frm.reload_doc();
                        }
                    },
                });
            }).addClass("btn-primary");

            frm.add_custom_button(__("Reject"), function () {
                frappe.prompt(
                    [
                        {
                            fieldname: "reason",
                            fieldtype: "Small Text",
                            label: __("Reject Reason"),
                            reqd: 1,
                        },
                    ],
                    function (values) {
                        frappe.call({
                            method: "request_center.api.requests.reject_request",
                            args: {
                                request_name: frm.doc.name,
                                reason: values.reason,
                            },
                            freeze: true,
                            callback: function (res) {
                                if (res.message) {
                                    frappe.show_alert({
                                        message: res.message.message,
                                        indicator: "red",
                                    });
                                    frm.reload_doc();
                                }
                            },
                        });
                    },
                    __("Reject Request"),
                    __("Reject")
                );
            });
        },
    });
}


function refresh_all_requirement_rows(frm) {
    if (!frm.fields_dict.requirements) return;

    setTimeout(() => {
        (frm.doc.requirements || []).forEach(row => {
            update_value_widget(frm, row.doctype, row.name);
        });
    }, 200);
}


function refresh_current_approver(frm) {
    if (!frm.doc.request_type) {
        if (frm.doc.current_approver) {
            frm.set_value("current_approver", "");
        }
        return;
    }

    frappe.call({
        method: "request_center.api.requests.get_approver_preview",
        args: {
            request_type: frm.doc.request_type,
            department: frm.doc.department,
            status: frm.doc.status,
        },
        callback: function (r) {
            if (!r.message) {
                return;
            }
            const approver = r.message.current_approver || "";
            const level = r.message.current_approval_level || "";
            if (frm.doc.current_approver !== approver) {
                frm.set_value("current_approver", approver);
            }
            if (frm.doc.current_approval_level !== level) {
                frm.set_value("current_approval_level", level);
            }
        },
    });
}



function update_value_widget(frm, cdt, cdn) {

    const row = locals[cdt][cdn];
    if (!row) return;

    const grid = frm.fields_dict.requirements.grid;
    const grid_row = grid.grid_rows_by_docname[cdn];
    if (!grid_row) return;

    const df = grid_row.docfields.find(d => d.fieldname === "value");
    if (!df) return;

    df.reqd = cint(row.is_mandatory);

    switch (row.field_type) {

        case "Date":
            df.fieldtype = "Date";
            df.options = "";
            break;

        case "Datetime":
            df.fieldtype = "Datetime";
            df.options = "";
            break;

        case "Check":
            df.fieldtype = "Check";
            df.options = "";
            break;

        case "Int":
            df.fieldtype = "Int";
            df.options = "";
            break;

        case "Number":
        case "Float":
            df.fieldtype = "Float";
            df.options = "";
            break;

        case "Currency":
            df.fieldtype = "Currency";
            df.options = "";
            break;

        case "Text":
            df.fieldtype = "Text";
            df.options = "";
            break;

        case "Text Area":
            df.fieldtype = "Small Text";
            df.options = "";
            break;

        case "Select":
            df.fieldtype = "Select";
            df.options = row.options || "";
            break;

        case "Link":
            df.fieldtype = "Link";
            df.options = (row.options || "").trim().split("\n")[0];
            break;

        default:
            df.fieldtype = "Data";
            df.options = "";
    }

    grid_row.refresh_field("value");
}