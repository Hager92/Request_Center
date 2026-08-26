# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from request_center.setup.purchase_links import stamp_existing_document


def ensure_tender_for_request(request_doc, notes: Optional[str] = None, external_reference: Optional[str] = None):
	existing = getattr(request_doc, "tender", None)
	if existing and frappe.db.exists("Tender", existing):
		tender = frappe.get_doc("Tender", existing)
		_fill_tender(tender, request_doc, notes, external_reference)
		tender.flags.ignore_permissions = True
		tender.save()
		_stamp_linked_material_request(tender, request_doc)
		copy_suppliers_to_request(tender)
		return tender

	tender = frappe.new_doc("Tender")
	tender.request = request_doc.name
	tender.title = _("Tender for {0}").format(request_doc.name)
	tender.status = "Open"
	tender.opening_date = nowdate()
	_fill_tender(tender, request_doc, notes, external_reference)
	tender.flags.ignore_permissions = True
	tender.insert(ignore_permissions=True)
	request_doc.tender = tender.name
	_stamp_linked_material_request(tender, request_doc)
	copy_suppliers_to_request(tender)
	return tender


def _fill_tender(tender, request_doc, notes: Optional[str], external_reference: Optional[str]) -> None:
	from request_center.material_fulfillment import _company

	tender.company = tender.company or _company()
	notes = notes or getattr(request_doc, "tender_notes", None)
	external_reference = external_reference or getattr(request_doc, "tender_reference", None)
	if notes:
		tender.notes = notes
	if external_reference:
		tender.external_reference = external_reference
	purchase_mrs = _purchase_material_requests(request_doc)
	if purchase_mrs and not tender.material_request:
		tender.material_request = purchase_mrs[0]
	_sync_items(tender, request_doc)
	_sync_suppliers(tender, request_doc)


def _purchase_material_requests(request_doc) -> List[str]:
	names = []
	for row in getattr(request_doc, "material_workflow", None) or []:
		if row.stage != "Purchase" or not row.document_name:
			continue
		names.extend([part.strip() for part in str(row.document_name).split(",") if part.strip()])
	if not names:
		for row in getattr(request_doc, "linked_documents", None) or []:
			if row.document_type == "Material Request" and row.purpose == "Purchase" and row.document_name:
				names.append(row.document_name)
	return names


def _sync_items(tender, request_doc) -> None:
	existing = {row.item_code: row for row in (tender.items or []) if row.item_code}
	for row in request_doc.material_items or []:
		qty = flt(getattr(row, "qty_to_purchase", None) or 0)
		if qty <= 0:
			path = getattr(row, "fulfillment_path", None) or ""
			if "Purchase" not in path:
				continue
			qty = flt(row.qty)
		if qty <= 0 or not row.item_code:
			continue
		target = existing.get(row.item_code)
		if target:
			target.qty = qty
			target.uom = row.uom or target.uom
			target.warehouse = row.warehouse or target.warehouse
			continue
		tender.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": qty,
				"uom": row.uom,
				"warehouse": row.warehouse,
			},
		)
	if tender.items:
		return
	for row in request_doc.material_items or []:
		if not row.item_code or flt(row.qty) <= 0:
			continue
		tender.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": flt(row.qty),
				"uom": row.uom,
				"warehouse": row.warehouse,
			},
		)


def _sync_suppliers(tender, request_doc) -> None:
	existing = {row.supplier for row in (tender.suppliers or []) if row.supplier}
	for row in request_doc.material_suppliers or []:
		if not row.supplier or row.supplier in existing:
			continue
		tender.append("suppliers", {"supplier": row.supplier})
		existing.add(row.supplier)


def copy_suppliers_to_request(tender) -> int:
	if isinstance(tender, str):
		if not tender or not frappe.db.exists("Tender", tender):
			return 0
		tender = frappe.get_doc("Tender", tender)
	request_name = getattr(tender, "request", None)
	if not request_name or not frappe.db.exists("Requests", request_name):
		return 0
	if not frappe.get_meta("Requests").has_field("material_suppliers"):
		return 0
	suppliers = []
	seen = set()
	for row in tender.suppliers or []:
		if not row.supplier or row.supplier in seen:
			continue
		suppliers.append(row.supplier)
		seen.add(row.supplier)
	if not suppliers:
		return 0
	existing = set(
		frappe.get_all(
			"Request Material Supplier",
			filters={"parent": request_name, "parenttype": "Requests", "parentfield": "material_suppliers"},
			pluck="supplier",
		)
	)
	max_idx = frappe.db.sql(
		"""
		select ifnull(max(idx), 0)
		from `tabRequest Material Supplier`
		where parent=%s and parenttype=%s and parentfield=%s
		""",
		(request_name, "Requests", "material_suppliers"),
	)[0][0]
	added = 0
	for supplier in suppliers:
		if supplier in existing:
			continue
		max_idx += 1
		row = frappe.new_doc("Request Material Supplier")
		row.parent = request_name
		row.parenttype = "Requests"
		row.parentfield = "material_suppliers"
		row.idx = max_idx
		row.supplier = supplier
		row.flags.ignore_permissions = True
		row.db_insert()
		existing.add(supplier)
		added += 1
	return added


@frappe.whitelist()
def sync_request_suppliers(tender_name: str) -> Dict[str, Any]:
	if not tender_name:
		frappe.throw(_("Tender is required"))
	added = copy_suppliers_to_request(tender_name)
	return {"status": "success", "copied": added}


def _stamp_linked_material_request(tender, request_doc) -> None:
	if not tender.material_request:
		return
	stamp_existing_document("Material Request", tender.material_request, request_doc.name)
	if tender.name:
		_stamp_tender("Material Request", tender.material_request, tender.name)


def attach_document_to_tender(request_doc, doctype: str, name: str) -> None:
	tender_name = getattr(request_doc, "tender", None)
	if not tender_name or not frappe.db.exists("Tender", tender_name):
		return
	tender = frappe.get_doc("Tender", tender_name)
	changed = False
	if doctype == "Request for Quotation":
		if name not in [row.request_for_quotation for row in (tender.rfqs or [])]:
			tender.append("rfqs", {"request_for_quotation": name})
			changed = True
	elif doctype == "Purchase Order":
		if name not in [row.purchase_order for row in (tender.purchase_orders or [])]:
			tender.append("purchase_orders", {"purchase_order": name})
			changed = True
	elif doctype == "Material Request" and not tender.material_request:
		tender.material_request = name
		changed = True
	if changed:
		tender.flags.ignore_permissions = True
		tender.save()
	stamp_existing_document(doctype, name, request_doc.name)
	_stamp_tender(doctype, name, tender.name)


def _stamp_tender(doctype: str, name: str, tender_name: str) -> None:
	if not frappe.db.exists(doctype, name):
		return
	if not frappe.get_meta(doctype).has_field("request_center_tender"):
		return
	if frappe.db.get_value(doctype, name, "request_center_tender") == tender_name:
		return
	frappe.db.set_value(doctype, name, "request_center_tender", tender_name, update_modified=False)


def record_tender_award(request_doc, quotation: str, supplier: str) -> None:
	tender_name = getattr(request_doc, "tender", None)
	if not tender_name or not frappe.db.exists("Tender", tender_name):
		return
	tender = frappe.get_doc("Tender", tender_name)
	tender.awarded_quotation = quotation
	tender.awarded_supplier = supplier
	tender.status = "Awarded"
	_upsert_offer(tender, quotation, supplier, awarded=True)
	tender.flags.ignore_permissions = True
	tender.save()
	_stamp_tender("Supplier Quotation", quotation, tender.name)


def _upsert_offer(tender, quotation: str, supplier: str, awarded: bool = False) -> None:
	grand_total = 0
	delivery = None
	status = "Received"
	if frappe.db.exists("Supplier Quotation", quotation):
		sq = frappe.get_doc("Supplier Quotation", quotation)
		supplier = supplier or sq.supplier
		grand_total = flt(sq.grand_total)
		dates = [getdate(row.expected_delivery_date) for row in sq.items if getattr(row, "expected_delivery_date", None)]
		delivery = min(dates) if dates else None
		if awarded:
			status = "Awarded"
		elif sq.docstatus == 1:
			status = "Submitted"
	for row in tender.offers or []:
		if row.supplier_quotation == quotation or (row.supplier == supplier and not row.supplier_quotation):
			row.supplier = supplier
			row.supplier_quotation = quotation
			row.grand_total = grand_total
			row.expected_delivery_date = delivery
			row.offer_status = "Awarded" if awarded else status
			return
	tender.append(
		"offers",
		{
			"supplier": supplier,
			"supplier_quotation": quotation,
			"grand_total": grand_total,
			"expected_delivery_date": delivery,
			"offer_status": "Awarded" if awarded else status,
		},
	)


@frappe.whitelist()
def sync_tender_offers(tender_name: str) -> Dict[str, Any]:
	tender = frappe.get_doc("Tender", tender_name)
	added = 0
	for row in tender.rfqs or []:
		if not row.request_for_quotation:
			continue
		names = frappe.get_all(
			"Supplier Quotation Item",
			filters={"request_for_quotation": row.request_for_quotation},
			pluck="parent",
		)
		if not names:
			continue
		quotes = frappe.get_all(
			"Supplier Quotation",
			filters={"name": ["in", list(set(names))]},
			fields=["name", "supplier", "grand_total", "docstatus"],
		)
		known = {offer.supplier_quotation for offer in (tender.offers or []) if offer.supplier_quotation}
		for quote in quotes:
			if quote.name in known:
				_upsert_offer(tender, quote.name, quote.supplier, awarded=quote.name == tender.awarded_quotation)
				continue
			_upsert_offer(tender, quote.name, quote.supplier, awarded=quote.name == tender.awarded_quotation)
			known.add(quote.name)
			added += 1
			_stamp_tender("Supplier Quotation", quote.name, tender.name)
	if tender.offers and tender.status in ("Draft", "Open"):
		tender.status = "Offers Received"
	tender.flags.ignore_permissions = True
	tender.save()
	return {
		"status": "success",
		"message": _("Supplier offers updated") if added or tender.offers else _("No supplier offers found yet"),
		"tender": tender.name,
	}
