# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

MATERIAL_CATEGORY = "Material Request"


def is_material_request(doc) -> bool:
	category = getattr(doc, "category", None)
	if not category and getattr(doc, "request_type", None):
		category = frappe.db.get_value("Request Type", doc.request_type, "category")
	return category == MATERIAL_CATEGORY


def try_start_material_fulfillment(request_name: str) -> Optional[Dict[str, Any]]:
	from request_center.material_workflow import try_start_material_fulfillment as _try_start

	return _try_start(request_name)


@frappe.whitelist()
def start_material_fulfillment(request_name: str) -> Dict[str, Any]:
	from request_center.material_workflow import run_inventory_check

	return run_inventory_check(request_name)


def _material_items(doc) -> List[Dict[str, Any]]:
	rows = []
	for row in getattr(doc, "material_items", None) or []:
		if not row.item_code or flt(row.qty) <= 0:
			continue
		rows.append(
			{
				"name": row.name,
				"item_code": row.item_code,
				"qty": flt(row.qty),
				"uom": row.uom,
				"warehouse": row.warehouse,
			}
		)
	return rows


def _company_warehouses(company: Optional[str]) -> Optional[set]:
	if not company or not frappe.db.exists("DocType", "Warehouse"):
		return None
	filters: Dict[str, Any] = {"is_group": 0}
	if company:
		filters["company"] = company
	if frappe.get_meta("Warehouse").has_field("disabled"):
		filters["disabled"] = 0
	return set(frappe.get_all("Warehouse", filters=filters, pluck="name"))


def _warehouse_stocks(item_code: str, company: Optional[str] = None) -> List[tuple]:
	if not frappe.db.get_value("Item", item_code, "is_stock_item"):
		return []
	if not frappe.db.table_exists("Bin"):
		return []
	allowed = _company_warehouses(company)
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": item_code, "actual_qty": [">", 0]},
		fields=["warehouse", "actual_qty"],
		order_by="actual_qty desc",
	)
	stocks = []
	for row in rows:
		if allowed is not None and row.warehouse not in allowed:
			continue
		qty = flt(row.actual_qty)
		if qty > 0:
			stocks.append((row.warehouse, qty))
	return stocks


def _stock_qty(item_code: str, warehouse: Optional[str] = None, company: Optional[str] = None) -> float:
	if warehouse:
		for wh, qty in _warehouse_stocks(item_code, company):
			if wh == warehouse:
				return qty
		return 0
	return sum(qty for _wh, qty in _warehouse_stocks(item_code, company))


def _company() -> str:
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		companies = frappe.get_all("Company", pluck="name", limit=1)
		company = companies[0] if companies else None
	if not company:
		frappe.throw(_("Set a default Company before starting Material Request fulfillment"))
	return company


def _default_warehouse(company: str) -> Optional[str]:
	warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
	if warehouse:
		return warehouse
	return frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")


def _conversion_factor(item_code: str, uom: Optional[str], stock_uom: Optional[str]) -> float:
	if not uom or not stock_uom or uom == stock_uom:
		return 1
	try:
		from erpnext.stock.get_item_details import get_conversion_factor

		return flt(get_conversion_factor(item_code, uom).get("conversion_factor")) or 1
	except Exception:
		return 1


def _create_erp_material_request(
	source, company: str, purpose: str, items: List[Dict[str, Any]]
) -> str:
	mr = frappe.new_doc("Material Request")
	mr.material_request_type = purpose
	mr.company = company
	mr.transaction_date = getdate(getattr(source, "request_date", None)) or nowdate()
	mr.schedule_date = nowdate()
	warehouses = {row.get("warehouse") for row in items if row.get("warehouse")}
	if len(warehouses) == 1:
		mr.set_warehouse = next(iter(warehouses))
	from_warehouses = {row.get("from_warehouse") for row in items if row.get("from_warehouse")}
	if purpose == "Material Transfer" and len(from_warehouses) == 1:
		mr.set_from_warehouse = next(iter(from_warehouses))
	for row in items:
		item_code = row["item_code"]
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
		uom = row.get("uom") or stock_uom
		item_row = {
			"item_code": item_code,
			"qty": row["qty"],
			"uom": uom,
			"stock_uom": stock_uom,
			"conversion_factor": _conversion_factor(item_code, uom, stock_uom),
			"warehouse": row.get("warehouse"),
			"schedule_date": row.get("schedule_date") or nowdate(),
		}
		if purpose == "Material Transfer" and row.get("from_warehouse"):
			item_row["from_warehouse"] = row["from_warehouse"]
		mr.append("items", item_row)
	from request_center.setup.purchase_links import stamp_request_link

	stamp_request_link(mr, getattr(source, "name", None))
	mr.flags.ignore_permissions = True
	mr.insert(ignore_permissions=True)
	return mr.name
