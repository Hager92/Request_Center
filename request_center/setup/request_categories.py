from typing import Dict, List

import frappe
from frappe import _

PREDEFINED_REQUEST_CATEGORIES: List[Dict[str, str]] = [
	{
		"category_name": "Service Request",
		"description": "Requests for services rather than goods or materials.",
	},
	{
		"category_name": "Material Request",
		"description": (
			"All material-related requests use this category. Approval Levels on the Request Type "
			"still determine who must approve. After those approvals the request follows a fixed "
			"workflow: Inventory Check, then Internal Transfer / Issuance if stock is available, "
			"or Purchase then Supplier Selection, Tender, RFQ, Supplier Comparison, Price + Delivery, "
			"PO, Delivery, and Completed. Purchase Request and Inventory / Issuance are not separate "
			"top-level categories, and this path is not configured through Approval Levels."
		),
	},
	{
		"category_name": "Disbursement Request",
		"description": "Requests involving payment or disbursement of funds.",
	},
	{
		"category_name": "Other Requests",
		"description": "Requests that do not fall under Service, Material, or Disbursement.",
	},
]

ALLOWED_REQUEST_CATEGORIES = {
	row["category_name"] for row in PREDEFINED_REQUEST_CATEGORIES
}

MATERIAL_CATEGORY_ALIASES = {
	"purchase request",
	"purchase",
	"inventory request",
	"issuance request",
	"inventory / issuance request",
	"inventory/issuance request",
	"inventory issuance request",
	"inventory / issuance",
	"material issuance",
}


def ensure_request_categories() -> None:
	if not frappe.db.table_exists("Request Category"):
		return

	for row in PREDEFINED_REQUEST_CATEGORIES:
		name = row["category_name"]
		if frappe.db.exists("Request Category", name):
			if frappe.db.get_value("Request Category", name, "description") != row["description"]:
				frappe.db.set_value("Request Category", name, "description", row["description"])
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Request Category",
				"category_name": name,
				"description": row["description"],
			}
		)
		doc.insert(ignore_permissions=True)

	if frappe.db.table_exists("Request Type") and frappe.db.has_column(
		"Request Type", "category"
	):
		frappe.db.sql(
			"""
			update `tabRequest Type`
			set category = %s
			where ifnull(category, '') = ''
			""",
			("Other Requests",),
		)

	frappe.db.commit()


def validate_request_category_name(category_name: str) -> None:
	if category_name in ALLOWED_REQUEST_CATEGORIES:
		return
	if (category_name or "").strip().lower() in MATERIAL_CATEGORY_ALIASES:
		frappe.throw(
			_(
				"Use Material Request. Purchase Request and Inventory / Issuance Request "
				"are not separate categories. Material requests are checked against inventory first."
			)
		)
	frappe.throw(
		_("Request Category must be one of: {0}").format(
			", ".join(sorted(ALLOWED_REQUEST_CATEGORIES))
		)
	)
