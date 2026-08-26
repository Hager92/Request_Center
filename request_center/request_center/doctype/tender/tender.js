// Copyright (c) 2026, Hager and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tender", {
	after_save(frm) {
		if (!frm.doc.request) {
			return;
		}
		frappe.call({
			method: "request_center.tender.sync_request_suppliers",
			args: { tender_name: frm.doc.name },
			callback: function (r) {
				if (r.message && r.message.copied) {
					frappe.show_alert({
						message: __("{0} supplier(s) copied to Request {1}", [r.message.copied, frm.doc.request]),
						indicator: "green",
					});
				}
			},
		});
	},
	refresh(frm) {
		if (frm.doc.request) {
			frm.add_custom_button(__("Open Request"), function () {
				frappe.set_route("Form", "Requests", frm.doc.request);
			});
		}
		if (frm.doc.material_request) {
			frm.add_custom_button(__("Open Material Request"), function () {
				frappe.set_route("Form", "Material Request", frm.doc.material_request);
			});
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Refresh Offers"), function () {
				frappe.call({
					method: "request_center.tender.sync_tender_offers",
					args: { tender_name: frm.doc.name },
					freeze: true,
					callback: function (r) {
						if (r.message) {
							frappe.msgprint(r.message.message);
							frm.reload_doc();
						}
					},
				});
			});
		}
		(frm.doc.rfqs || []).forEach(function (row) {
			if (!row.request_for_quotation) {
				return;
			}
			frm.add_custom_button(row.request_for_quotation, function () {
				frappe.set_route("Form", "Request for Quotation", row.request_for_quotation);
			}, __("RFQs"));
		});
		(frm.doc.purchase_orders || []).forEach(function (row) {
			if (!row.purchase_order) {
				return;
			}
			frm.add_custom_button(row.purchase_order, function () {
				frappe.set_route("Form", "Purchase Order", row.purchase_order);
			}, __("Purchase Orders"));
		});
	},
});
