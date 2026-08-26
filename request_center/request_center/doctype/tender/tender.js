// Copyright (c) 2026, Hager and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tender", {
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
		if (!frm.is_new() && frm.doc.request && !(frm.doc.rfqs || []).some((row) => row.request_for_quotation)) {
			frm.add_custom_button(__("Create and Send RFQ"), function () {
				frappe.confirm(__("Create and send an RFQ to the suppliers selected on this Tender?"), function () {
					frappe.call({
						method: "request_center.rfq.create_and_send_rfq",
						args: { request_name: frm.doc.request },
						freeze: true,
						callback: function (r) {
							if (r.message) {
								frappe.msgprint(r.message.message);
								frm.reload_doc();
							}
						},
					});
				});
			}).addClass("btn-primary");
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
