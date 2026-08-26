# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from request_center.rfq import _purchase_material_request
from request_center.setup.purchase_links import (
	MATERIAL_REQUEST_LINK_FIELD,
	stamp_request_link,
)


def _submit_if_draft(doctype: str, name: str) -> None:
	if not name or not frappe.db.exists(doctype, name):
		return
	target = frappe.get_doc(doctype, name)
	if target.docstatus == 0:
		target.flags.ignore_permissions = True
		target.submit()


def _existing_purchase_order(request_doc) -> Optional[str]:
	if getattr(request_doc, "purchase_order", None) and frappe.db.exists(
		"Purchase Order", request_doc.purchase_order
	):
		return request_doc.purchase_order
	for row in getattr(request_doc, "material_workflow", None) or []:
		if row.stage == "PO" and row.document_name:
			name = str(row.document_name).split(",")[0].strip()
			if name and frappe.db.exists("Purchase Order", name):
				return name
	for row in getattr(request_doc, "linked_documents", None) or []:
		if row.document_type == "Purchase Order" and row.document_name:
			if frappe.db.exists("Purchase Order", row.document_name):
				return row.document_name
	if getattr(request_doc, "tender", None) and frappe.db.exists("Tender", request_doc.tender):
		tender = frappe.get_doc("Tender", request_doc.tender)
		for row in tender.purchase_orders or []:
			if row.purchase_order and frappe.db.exists("Purchase Order", row.purchase_order):
				return row.purchase_order
	return None


def _awarded_supplier(request_doc, quotation: str) -> str:
	supplier = getattr(request_doc, "awarded_supplier", None)
	if supplier:
		return supplier
	if quotation and frappe.db.exists("Supplier Quotation", quotation):
		return frappe.db.get_value("Supplier Quotation", quotation, "supplier")
	frappe.throw(_("Select a supplier in Supplier Comparison before creating a Purchase Order"))


def _link_items_to_material_request(po, mr_name: Optional[str]) -> None:
	if not mr_name or not frappe.db.exists("Material Request", mr_name):
		return
	if po.meta.has_field(MATERIAL_REQUEST_LINK_FIELD):
		po.set(MATERIAL_REQUEST_LINK_FIELD, mr_name)
	mr_items = frappe.get_all(
		"Material Request Item",
		filters={"parent": mr_name},
		fields=["name", "item_code"],
		order_by="idx",
	)
	available: Dict[str, List[str]] = {}
	for row in mr_items:
		available.setdefault(row.item_code, []).append(row.name)
	used = set()
	for item in po.items or []:
		if item.material_request_item and item.material_request_item not in used:
			item.material_request = mr_name
			used.add(item.material_request_item)
			continue
		candidates = available.get(item.item_code) or []
		chosen = next((name for name in candidates if name not in used), None)
		if not chosen and candidates:
			chosen = candidates[0]
		if chosen:
			item.material_request = mr_name
			item.material_request_item = chosen
			used.add(chosen)


def _stamp_po_links(po, request_doc, mr_name: Optional[str]) -> None:
	stamp_request_link(po, request_doc.name)
	tender_name = getattr(request_doc, "tender", None)
	if tender_name and po.meta.has_field("request_center_tender"):
		po.set("request_center_tender", tender_name)
	_link_items_to_material_request(po, mr_name)


def create_purchase_order_for_request(request_doc) -> Dict[str, Any]:
	quotation = getattr(request_doc, "selected_quotation", None)
	if not quotation:
		frappe.throw(_("Compare supplier quotations and select a supplier before creating a Purchase Order"))
	if not frappe.db.exists("Supplier Quotation", quotation):
		frappe.throw(_("Supplier Quotation {0} does not exist").format(quotation))

	existing = _existing_purchase_order(request_doc)
	if existing:
		po = frappe.get_doc("Purchase Order", existing)
		mr_name = _purchase_material_request(request_doc)
		_stamp_po_links(po, request_doc, mr_name)
		from request_center.tender import attach_document_to_tender

		attach_document_to_tender(request_doc, "Purchase Order", po.name)
		if po.docstatus == 0:
			po.flags.ignore_permissions = True
			po.save()
		request_doc.purchase_order = po.name
		return {
			"purchase_order": po.name,
			"supplier": po.supplier,
			"material_request": mr_name,
			"tender": getattr(request_doc, "tender", None),
			"message": _po_message(po.name, po.supplier, request_doc.name, mr_name, request_doc.tender),
		}

	_submit_if_draft("Supplier Quotation", quotation)
	from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order

	po = make_purchase_order(quotation)
	supplier = _awarded_supplier(request_doc, quotation)
	if supplier:
		po.supplier = supplier
	if getattr(request_doc, "expected_delivery_date", None):
		po.schedule_date = request_doc.expected_delivery_date
		for row in po.items:
			if not row.schedule_date:
				row.schedule_date = request_doc.expected_delivery_date
	mr_name = _purchase_material_request(request_doc)
	_stamp_po_links(po, request_doc, mr_name)
	po.flags.ignore_permissions = True
	po.insert(ignore_permissions=True)
	request_doc.purchase_order = po.name
	from request_center.tender import attach_document_to_tender

	attach_document_to_tender(request_doc, "Purchase Order", po.name)
	return {
		"purchase_order": po.name,
		"supplier": po.supplier,
		"material_request": mr_name,
		"tender": getattr(request_doc, "tender", None),
		"message": _po_message(po.name, po.supplier, request_doc.name, mr_name, request_doc.tender),
	}


def _po_message(
	po_name: str,
	supplier: Optional[str],
	request_name: str,
	mr_name: Optional[str],
	tender_name: Optional[str],
) -> str:
	parts = [_("Purchase Order {0} created for supplier {1}.").format(po_name, supplier or _("the selected supplier"))]
	links = [_("Purchase Requisition {0}").format(request_name)]
	if mr_name:
		links.append(_("Material Request {0}").format(mr_name))
	if tender_name:
		links.append(_("Tender {0}").format(tender_name))
	parts.append(_("Linked to {0}.").format(", ".join(links)))
	return " ".join(parts)
