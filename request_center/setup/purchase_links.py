# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

REQUEST_LINK_FIELD = "request_center_request"
TENDER_LINK_FIELD = "request_center_tender"
MATERIAL_REQUEST_LINK_FIELD = "request_center_material_request"

PURCHASE_LINK_DOCTYPES = [
	"Material Request",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Order",
	"Purchase Receipt",
	"Stock Entry",
]

TENDER_LINK_DOCTYPES = [
	"Material Request",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Order",
]


def ensure_purchase_document_links() -> None:
	if "erpnext" not in frappe.get_installed_apps():
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	field = {
		"fieldname": REQUEST_LINK_FIELD,
		"label": "Purchase Requisition",
		"fieldtype": "Link",
		"options": "Requests",
		"read_only": 1,
		"print_hide": 1,
		"translatable": 0,
		"no_copy": 1,
		"search_index": 1,
		"description": "Original Request Center Material Request / purchase requisition this document was created from.",
	}
	custom_fields = {
		doctype: [dict(field)]
		for doctype in PURCHASE_LINK_DOCTYPES
		if frappe.db.exists("DocType", doctype)
	}
	tender_field = {
		"fieldname": TENDER_LINK_FIELD,
		"label": "Tender",
		"fieldtype": "Link",
		"options": "Tender",
		"read_only": 1,
		"print_hide": 1,
		"translatable": 0,
		"no_copy": 1,
		"search_index": 1,
		"description": "Tender used to collect supplier offers for this purchasing document.",
	}
	for doctype in TENDER_LINK_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		custom_fields.setdefault(doctype, []).append(dict(tender_field))
	if frappe.db.exists("DocType", "Purchase Order"):
		custom_fields.setdefault("Purchase Order", []).append(
			{
				"fieldname": MATERIAL_REQUEST_LINK_FIELD,
				"label": "Material Request",
				"fieldtype": "Link",
				"options": "Material Request",
				"read_only": 1,
				"print_hide": 1,
				"translatable": 0,
				"no_copy": 1,
				"search_index": 1,
				"description": "ERPNext Material Request this Purchase Order fulfills.",
			}
		)
	if not custom_fields:
		return
	create_custom_fields(custom_fields, ignore_validate=True, update=True)


def stamp_request_link(target, request_name: str) -> None:
	if not request_name or not target:
		return
	if getattr(target, "meta", None) and target.meta.has_field(REQUEST_LINK_FIELD):
		target.set(REQUEST_LINK_FIELD, request_name)


def stamp_existing_document(doctype: str, name: str, request_name: str) -> None:
	if not doctype or not name or not request_name:
		return
	if not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, name):
		return
	if not frappe.get_meta(doctype).has_field(REQUEST_LINK_FIELD):
		return
	current = frappe.db.get_value(doctype, name, REQUEST_LINK_FIELD)
	if current == request_name:
		return
	frappe.db.set_value(doctype, name, REQUEST_LINK_FIELD, request_name, update_modified=False)
