// Copyright (c) 2026, Hager and contributors
// For license information, please see license.txt

frappe.ui.form.on("Request Type", {
	refresh(frm) {
		if (frm.fields_dict.requirements && frm.fields_dict.requirements.grid) {
			frm.fields_dict.requirements.grid.cannot_add_rows = false;
			frm.fields_dict.requirements.grid.cannot_delete_rows = false;
		}
		if (frm.fields_dict.approval_levels && frm.fields_dict.approval_levels.grid) {
			frm.fields_dict.approval_levels.grid.cannot_add_rows = false;
			frm.fields_dict.approval_levels.grid.cannot_delete_rows = false;
		}
		frm.set_query("approver", "approval_levels", function () {
			return {
				filters: {
					status: "Active",
					user_id: ["is", "set"],
				},
			};
		});
		show_request_type_intro(frm);
	},
	category(frm) {
		show_request_type_intro(frm);
		if (frm.doc.category === "Material Request" && !frm.doc.comparison_method) {
			frm.set_value("comparison_method", "Weighted Score");
			frm.set_value("price_weight", 50);
			frm.set_value("delivery_weight", 50);
			frm.set_value("rank_primary", "Price");
		}
	},
	comparison_method(frm) {
		if (frm.doc.comparison_method === "Weighted Score") {
			if (frm.doc.price_weight == null) {
				frm.set_value("price_weight", 50);
			}
			if (frm.doc.delivery_weight == null) {
				frm.set_value("delivery_weight", 50);
			}
		}
	},
	price_weight(frm) {
		sync_comparison_weights(frm, "price");
	},
	delivery_weight(frm) {
		sync_comparison_weights(frm, "delivery");
	},
});

frappe.ui.form.on("Request Type Requirement", {
	field_label(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.field_label) {
			return;
		}
		if (!row.field_key) {
			frappe.model.set_value(cdt, cdn, "field_key", slug_field_key(row.field_label));
		}
	},
});

frappe.ui.form.on("Request Type Approval Level", {
	approval_levels_add(frm, cdt, cdn) {
		const others = (frm.doc.approval_levels || []).filter((row) => row.name !== cdn);
		const next_level = others.reduce((max, row) => Math.max(max, row.level || 0), 0) + 1;
		frappe.model.set_value(cdt, cdn, "level", next_level);
		frappe.model.set_value(cdt, cdn, "required", 1);
	},
});

function slug_field_key(fieldName) {
	return String(fieldName || "")
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "_")
		.replace(/^_+|_+$/g, "") || "field";
}

function sync_comparison_weights(frm, changed) {
	if (frm.doc.comparison_method !== "Weighted Score") {
		return;
	}
	if (frm._syncing_comparison_weights) {
		return;
	}
	frm._syncing_comparison_weights = true;
	try {
		if (changed === "price") {
			const delivery = 100 - flt(frm.doc.price_weight);
			if (flt(frm.doc.delivery_weight) !== flt(delivery)) {
				frm.set_value("delivery_weight", delivery);
			}
		} else {
			const price = 100 - flt(frm.doc.delivery_weight);
			if (flt(frm.doc.price_weight) !== flt(price)) {
				frm.set_value("price_weight", price);
			}
		}
	} finally {
		frm._syncing_comparison_weights = false;
	}
}

function show_request_type_intro(frm) {
	frm.set_intro("");
	const parts = [
		__(
			"Configure this Request Type here: Request Category, Department, Dynamic Form Fields, Mandatory Fields, Approval Levels, Approvers, and Approval Sequence."
		),
	];
	if (frm.doc.category === "Material Request") {
		parts.push(
			__(
				"After Approval Levels, Material Request follows a fixed workflow: Inventory Check, then Internal Transfer / Issuance if stock is available, or Purchase (Supplier Selection, Tender, RFQ, Supplier Comparison, Purchase Order, Delivery). Purchasing Policy on this page controls how Price and Delivery Time are compared."
			)
		);
	} else {
		parts.push(
			__(
				"After Approval Levels, this type uses an existing Execution Mode (HR, Internal Service, IT, Inventory, Purchase, or External)."
			)
		);
	}
	frm.set_intro(parts.join(" "), "blue");
}
