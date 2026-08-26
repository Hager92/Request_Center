# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from request_center.setup.purchase_links import stamp_existing_document, stamp_request_link


def _tender_and_suppliers(request_doc) -> Tuple[Optional[Any], List[str]]:
	tender = None
	tender_name = getattr(request_doc, "tender", None)
	if tender_name and frappe.db.exists("Tender", tender_name):
		tender = frappe.get_doc("Tender", tender_name)
		suppliers = [row.supplier for row in (tender.suppliers or []) if row.supplier]
		if suppliers:
			return tender, suppliers
	suppliers = [row.supplier for row in (request_doc.material_suppliers or []) if row.supplier]
	return tender, suppliers


def _existing_rfq(request_doc) -> Optional[str]:
	if getattr(request_doc, "rfq", None) and frappe.db.exists("Request for Quotation", request_doc.rfq):
		return request_doc.rfq
	for row in getattr(request_doc, "material_workflow", None) or []:
		if row.stage == "RFQ" and row.document_name:
			name = str(row.document_name).split(",")[0].strip()
			if name and frappe.db.exists("Request for Quotation", name):
				return name
	for row in getattr(request_doc, "linked_documents", None) or []:
		if row.document_type == "Request for Quotation" and row.document_name:
			if frappe.db.exists("Request for Quotation", row.document_name):
				return row.document_name
	if getattr(request_doc, "tender", None) and frappe.db.exists("Tender", request_doc.tender):
		tender = frappe.get_doc("Tender", request_doc.tender)
		for row in tender.rfqs or []:
			if row.request_for_quotation and frappe.db.exists("Request for Quotation", row.request_for_quotation):
				return row.request_for_quotation
	return None


def _contact_and_email(supplier: str) -> Tuple[Optional[str], Optional[str]]:
	contact = None
	try:
		from frappe.contacts.doctype.contact.contact import get_default_contact

		contact = get_default_contact("Supplier", supplier)
	except Exception:
		contact = None
	email = frappe.db.get_value("Contact", contact, "email_id") if contact else None
	if not email and frappe.get_meta("Supplier").has_field("email_id"):
		email = frappe.db.get_value("Supplier", supplier, "email_id")
	return contact, email or None


def _portal_route() -> Optional[str]:
	return frappe.db.get_value("Portal Menu Item", {"reference_doctype": "Request for Quotation"}, "route")


def _append_suppliers(rfq, suppliers: List[str], send_if_possible: bool = True) -> None:
	rfq.set("suppliers", [])
	can_send = send_if_possible and bool(_portal_route())
	for supplier in suppliers:
		contact, email = _contact_and_email(supplier)
		rfq.append(
			"suppliers",
			{
				"supplier": supplier,
				"contact": contact,
				"email_id": email,
				"send_email": 1 if can_send and email else 0,
			},
		)


def _purchase_material_request(request_doc) -> Optional[str]:
	for row in getattr(request_doc, "material_workflow", None) or []:
		if row.stage == "Purchase" and row.document_name:
			name = str(row.document_name).split(",")[0].strip()
			if name and frappe.db.exists("Material Request", name):
				return name
	for row in getattr(request_doc, "linked_documents", None) or []:
		if row.document_type == "Material Request" and row.purpose == "Purchase" and row.document_name:
			return row.document_name
	tender_name = getattr(request_doc, "tender", None)
	if tender_name:
		mr = frappe.db.get_value("Tender", tender_name, "material_request")
		if mr:
			return mr
	return None


def _submit_if_draft(doctype: str, name: str) -> None:
	if not name or not frappe.db.exists(doctype, name):
		return
	target = frappe.get_doc(doctype, name)
	if target.docstatus == 0:
		target.flags.ignore_permissions = True
		target.submit()


def _build_rfq(request_doc, tender, suppliers: List[str]):
	mr_name = _purchase_material_request(request_doc)
	rfq = None
	if mr_name:
		_submit_if_draft("Material Request", mr_name)
		try:
			from erpnext.stock.doctype.material_request.material_request import make_request_for_quotation

			rfq = make_request_for_quotation(mr_name)
		except Exception:
			rfq = None
	if rfq is None:
		from frappe.utils import flt
		from request_center.material_fulfillment import _company

		rfq = frappe.new_doc("Request for Quotation")
		rfq.company = _company()
		rfq.transaction_date = nowdate()
		source_items = list(tender.items) if tender and tender.items else []
		if not source_items:
			for row in request_doc.material_items or []:
				if row.item_code:
					source_items.append(row)
		for row in source_items:
			qty = flt(getattr(row, "qty_to_purchase", None) or row.qty)
			if qty <= 0:
				continue
			rfq.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": qty,
					"uom": getattr(row, "uom", None),
					"warehouse": getattr(row, "warehouse", None),
					"schedule_date": nowdate(),
				},
			)
	if not rfq.items:
		frappe.throw(_("Add requested products before creating an RFQ"))
	title = tender.title if tender else request_doc.name
	rfq.subject = _("Request for Quotation — {0}").format(title)
	rfq.message_for_supplier = _(
		"Please quote your best price and expected delivery time for the requested materials."
	)
	if not rfq.schedule_date:
		rfq.schedule_date = nowdate()
	_append_suppliers(rfq, suppliers)
	return rfq


def _submit_rfq(rfq) -> None:
	if rfq.docstatus == 1:
		return
	rfq.flags.ignore_permissions = True
	try:
		rfq.submit()
	except Exception:
		if cint(getattr(rfq, "docstatus", 0)) == 1:
			return
		for row in rfq.suppliers:
			row.send_email = 0
		rfq.flags.ignore_permissions = True
		rfq.submit()


def _send_rfq(rfq) -> List[str]:
	if rfq.docstatus != 1:
		return []
	sent = [row.supplier for row in rfq.suppliers if row.email_sent]
	if sent:
		return sent
	if not _portal_route():
		return []
	changed = False
	for row in rfq.suppliers:
		if row.email_id and not row.email_sent:
			row.send_email = 1
			changed = True
	if not changed:
		return []
	try:
		rfq.flags.ignore_permissions = True
		rfq.send_to_supplier()
	except Exception:
		frappe.log_error(title=_("Could not email RFQ {0}").format(rfq.name))
	return [row.supplier for row in rfq.suppliers if row.email_sent]


def _quotation_exists(rfq_name: str, supplier: str) -> Optional[str]:
	rows = frappe.db.sql(
		"""
		select sq.name
		from `tabSupplier Quotation` sq
		inner join `tabSupplier Quotation Item` item on item.parent = sq.name
		where sq.supplier = %s and item.request_for_quotation = %s and sq.docstatus < 2
		limit 1
		""",
		(supplier, rfq_name),
	)
	return rows[0][0] if rows else None


def _ensure_offer_drafts(rfq, request_doc) -> List[str]:
	from erpnext.buying.doctype.request_for_quotation.request_for_quotation import (
		make_supplier_quotation_from_rfq,
	)
	from request_center.tender import attach_document_to_tender, sync_tender_offers

	quotations = []
	attach_document_to_tender(request_doc, "Request for Quotation", rfq.name)
	for row in rfq.suppliers or []:
		if not row.supplier:
			continue
		existing = _quotation_exists(rfq.name, row.supplier)
		if existing:
			stamp_existing_document("Supplier Quotation", existing, request_doc.name)
			quotations.append(existing)
			continue
		try:
			sq = make_supplier_quotation_from_rfq(rfq.name, for_supplier=row.supplier)
			stamp_request_link(sq, request_doc.name)
			if request_doc.tender and sq.meta.has_field("request_center_tender"):
				sq.set("request_center_tender", request_doc.tender)
			sq.flags.ignore_permissions = True
			sq.insert(ignore_permissions=True)
			quotations.append(sq.name)
		except Exception:
			frappe.log_error(title=_("Could not create offer draft for {0}").format(row.supplier))
	if getattr(request_doc, "tender", None) and frappe.db.exists("Tender", request_doc.tender):
		sync_tender_offers(request_doc.tender)
	return quotations


def create_and_send_rfq_for_request(request_doc) -> Dict[str, Any]:
	tender, suppliers = _tender_and_suppliers(request_doc)
	if not suppliers:
		frappe.throw(_("Select suppliers on the Tender before creating an RFQ"))

	existing = _existing_rfq(request_doc)
	if existing:
		rfq = frappe.get_doc("Request for Quotation", existing)
		if rfq.docstatus == 0:
			_append_suppliers(rfq, suppliers)
			rfq.flags.ignore_permissions = True
			rfq.save()
			_submit_rfq(rfq)
			rfq.reload()
		sent = _send_rfq(rfq)
	else:
		rfq = _build_rfq(request_doc, tender, suppliers)
		stamp_request_link(rfq, request_doc.name)
		if request_doc.tender and rfq.meta.has_field("request_center_tender"):
			rfq.set("request_center_tender", request_doc.tender)
		rfq.flags.ignore_permissions = True
		rfq.insert(ignore_permissions=True)
		_submit_rfq(rfq)
		rfq.reload()
		sent = _send_rfq(rfq)

	request_doc.rfq = rfq.name
	quotations = _ensure_offer_drafts(rfq, request_doc)
	not_sent = [row.supplier for row in rfq.suppliers if row.supplier and row.supplier not in sent]
	return {
		"rfq": rfq.name,
		"suppliers": suppliers,
		"sent": sent,
		"not_sent": not_sent,
		"drafts": quotations,
		"message": _rfq_message(rfq.name, suppliers, sent, not_sent, quotations),
	}


def _rfq_message(rfq_name: str, suppliers: List[str], sent: List[str], not_sent: List[str], drafts: List[str]) -> str:
	parts = [_("RFQ {0} created for {1}.").format(rfq_name, ", ".join(suppliers))]
	if sent:
		parts.append(_("Sent to {0}.").format(", ".join(sent)))
	if not_sent:
		parts.append(
			_("No email was sent to {0}. Enter their Supplier Quotation offers, then compare.").format(
				", ".join(not_sent)
			)
		)
	if drafts:
		parts.append(_("Draft offers created so suppliers can provide price and delivery time."))
	else:
		parts.append(_("Supplier offers against this RFQ will be available for comparison once submitted."))
	return " ".join(parts)


@frappe.whitelist()
def create_and_send_rfq(request_name: str) -> Dict[str, Any]:
	from request_center.material_workflow import _require_erpnext, _require_fulfillment_role, _save

	_require_fulfillment_role()
	_require_erpnext()
	if not request_name:
		frappe.throw(_("Request is required"))
	doc = frappe.get_doc("Requests", request_name)
	if getattr(doc, "category", None) != "Material Request":
		frappe.throw(_("RFQ is only used on Material Requests"))
	result = create_and_send_rfq_for_request(doc)
	_save(doc)
	result["status"] = "success"
	return result
