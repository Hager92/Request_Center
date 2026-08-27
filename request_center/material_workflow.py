# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from request_center.material_fulfillment import (
	_company,
	_create_erp_material_request,
	_default_warehouse,
	_material_items,
	_warehouse_stocks,
	is_material_request,
)
from request_center.setup.purchase_links import stamp_existing_document, stamp_request_link

# Request Center architecture (Material Request after approval):
# Inventory Check → Available → Transfer
#                 → Not Available → Purchase → Tender → RFQ → Price + Delivery Comparison → PO → Delivery → Completed
STAGE_INVENTORY_CHECK = "Inventory Check"
STAGE_ISSUANCE = "Internal Transfer / Issuance"
STAGE_PURCHASE = "Purchase"
STAGE_SUPPLIER_SELECTION = "Supplier Selection"
STAGE_TENDER = "Tender"
STAGE_RFQ = "RFQ"
STAGE_COMPARISON = "Supplier Comparison"
STAGE_PRICE_DELIVERY = "Price + Delivery"
STAGE_PO = "PO"
STAGE_DELIVERY = "Delivery"
STAGE_COMPLETED = "Completed"

WORKFLOW_STEPS = [
	(1, STAGE_INVENTORY_CHECK, "Common"),
	(2, STAGE_ISSUANCE, "Inventory"),
	(3, STAGE_PURCHASE, "Purchase"),
	(4, STAGE_SUPPLIER_SELECTION, "Purchase"),
	(5, STAGE_TENDER, "Purchase"),
	(6, STAGE_RFQ, "Purchase"),
	(7, STAGE_COMPARISON, "Purchase"),
	(8, STAGE_PRICE_DELIVERY, "Purchase"),
	(9, STAGE_PO, "Purchase"),
	(10, STAGE_DELIVERY, "Purchase"),
	(11, STAGE_COMPLETED, "Common"),
]

PURCHASE_STAGES = [
	STAGE_PURCHASE,
	STAGE_SUPPLIER_SELECTION,
	STAGE_TENDER,
	STAGE_RFQ,
	STAGE_COMPARISON,
	STAGE_PRICE_DELIVERY,
	STAGE_PO,
	STAGE_DELIVERY,
]

ADVANCE_LABELS = {
	STAGE_INVENTORY_CHECK: _("Run Inventory Check"),
	STAGE_ISSUANCE: _("Create Issuance / Transfer"),
	STAGE_PURCHASE: _("Start Purchase"),
	STAGE_SUPPLIER_SELECTION: _("Confirm Suppliers"),
	STAGE_TENDER: _("Tender"),
	STAGE_RFQ: _("Create and Send RFQ"),
	STAGE_COMPARISON: _("Compare Quotations"),
	STAGE_PRICE_DELIVERY: _("Confirm Price and Delivery"),
	STAGE_PO: _("Create Purchase Order"),
	STAGE_DELIVERY: _("Record Delivery"),
	STAGE_COMPLETED: _("Complete Request"),
}


def _require_erpnext() -> None:
	if "erpnext" not in frappe.get_installed_apps() or not frappe.db.exists("DocType", "Material Request"):
		frappe.throw(_("ERPNext is required for the Material Request workflow"))


def _require_fulfillment_role() -> None:
	if frappe.session.user == "Administrator":
		return
	if set(frappe.get_roles()) & {"System Manager", "Execution Team"}:
		return
	frappe.throw(_("Only the Execution Team can advance the Material Request workflow"))


def _save(doc) -> None:
	doc.flags.ignore_permissions = True
	doc.flags.request_center_workflow = True
	doc.save()


def init_material_workflow(doc) -> None:
	if getattr(doc, "material_workflow", None):
		return
	for step, stage, branch in WORKFLOW_STEPS:
		doc.append(
			"material_workflow",
			{
				"step": step,
				"stage": stage,
				"branch": branch,
				"step_status": "Current" if stage == STAGE_INVENTORY_CHECK else "Pending",
			},
		)
	doc.fulfillment_stage = STAGE_INVENTORY_CHECK


def _row(doc, stage: str):
	for row in doc.material_workflow or []:
		if row.stage == stage:
			return row
	return None


def _set_step(
	doc,
	stage: str,
	status: str,
	document_type: Optional[str] = None,
	document_name: Optional[str] = None,
	remarks: Optional[str] = None,
) -> None:
	row = _row(doc, stage)
	if not row:
		return
	row.step_status = status
	if document_type:
		row.document_type = document_type
	if document_name:
		row.document_name = document_name
	if remarks is not None:
		row.remarks = remarks


def _status_of(doc, stage: str) -> str:
	row = _row(doc, stage)
	return row.step_status if row else "Pending"


def _refresh_stage(doc) -> None:
	current = [row.stage for row in (doc.material_workflow or []) if row.step_status == "Current"]
	if current:
		doc.fulfillment_stage = current[0]
		return
	if _status_of(doc, STAGE_COMPLETED) == "Done":
		doc.fulfillment_stage = STAGE_COMPLETED
		return
	pending = [row.stage for row in (doc.material_workflow or []) if row.step_status == "Pending"]
	doc.fulfillment_stage = pending[0] if pending else STAGE_COMPLETED


def _link_execution(doc, doctype: str, name: str) -> None:
	_link_document(doc, doctype, name, getattr(doc, "fulfillment_stage", None), "Purchase")


def _link_document(
	doc,
	doctype: str,
	name: str,
	stage: Optional[str] = None,
	purpose: str = "Purchase",
) -> None:
	if not doctype or not name:
		return
	doc.execution_doctype = doctype
	doc.execution_docname = name
	stamp_existing_document(doctype, name, doc.name)
	if not hasattr(doc, "linked_documents"):
		return
	for row in doc.linked_documents or []:
		if row.document_type == doctype and row.document_name == name:
			row.stage = stage or row.stage
			row.purpose = purpose or row.purpose
			return
	doc.append(
		"linked_documents",
		{
			"document_type": doctype,
			"document_name": name,
			"stage": stage,
			"purpose": purpose,
		},
	)


def _path_for(issue_qty: float, transfer_qty: float, purchase_qty: float) -> str:
	parts = []
	if issue_qty > 0:
		parts.append("Inventory")
	if transfer_qty > 0:
		parts.append("Internal Transfer")
	if purchase_qty > 0:
		parts.append("Purchase")
	if not parts:
		return "Purchase"
	if parts == ["Inventory", "Internal Transfer", "Purchase"]:
		return "Inventory, Internal Transfer and Purchase"
	return " and ".join(parts)


def _allocate_items(doc) -> Dict[str, List[Dict[str, Any]]]:
	company = _company()
	warehouse_default = _default_warehouse(company)
	buckets = {"issue": [], "transfer": [], "purchase": []}
	paths = []

	for row in _material_items(doc):
		item_code = row["item_code"]
		if not frappe.db.exists("Item", item_code):
			frappe.throw(_("Item {0} does not exist").format(item_code))
		qty = flt(row["qty"])
		stocks = _warehouse_stocks(item_code, company)
		stock_by_wh = {wh: available for wh, available in stocks}
		total_available = sum(stock_by_wh.values())
		target = row.get("warehouse") or warehouse_default
		if not target and stocks:
			target = stocks[0][0]
		if not target:
			frappe.throw(
				_(
					"Set a Warehouse on each material item, or a default warehouse in Stock Settings, "
					"before running Inventory Check"
				)
			)

		local = flt(stock_by_wh.get(target) or 0)
		issue_qty = min(qty, max(local, 0))
		remaining = flt(qty - issue_qty)
		transfer_qty = 0.0
		first_from_warehouse = None
		uom = row.get("uom") or frappe.db.get_value("Item", item_code, "stock_uom")
		base = {
			"item_code": item_code,
			"warehouse": target,
			"uom": uom,
			"schedule_date": nowdate(),
		}
		if issue_qty > 0:
			buckets["issue"].append({**base, "qty": issue_qty})
		if remaining > 0:
			for warehouse, available in stocks:
				if remaining <= 0:
					break
				if warehouse == target:
					continue
				take = min(remaining, available)
				if take <= 0:
					continue
				if not first_from_warehouse:
					first_from_warehouse = warehouse
				transfer_qty += take
				remaining = flt(remaining - take)
				buckets["transfer"].append({**base, "qty": take, "from_warehouse": warehouse})
		purchase_qty = remaining
		if purchase_qty > 0:
			buckets["purchase"].append({**base, "qty": purchase_qty})

		path = _path_for(issue_qty, transfer_qty, purchase_qty)
		paths.append(path)
		for item_row in doc.material_items or []:
			if item_row.name != row["name"]:
				continue
			item_row.stock_qty_available = total_available
			item_row.qty_to_issue = issue_qty
			item_row.qty_to_transfer = transfer_qty
			item_row.qty_to_purchase = purchase_qty
			item_row.fulfillment_path = path
			item_row.warehouse = target
			if first_from_warehouse:
				item_row.from_warehouse = first_from_warehouse
			break

	has_inventory = bool(buckets["issue"] or buckets["transfer"])
	has_purchase = bool(buckets["purchase"])
	if has_inventory and has_purchase:
		doc.inventory_check_result = "Partially Available"
		doc.fulfillment_path = "Inventory and Purchase"
	elif has_inventory:
		doc.inventory_check_result = "Available"
		unique_paths = []
		for path in paths:
			if path not in unique_paths:
				unique_paths.append(path)
		doc.fulfillment_path = unique_paths[0] if len(unique_paths) == 1 else "Inventory and Internal Transfer"
	else:
		doc.inventory_check_result = "Not Available"
		doc.fulfillment_path = "Purchase"
	return buckets


@frappe.whitelist()
def start_material_fulfillment(request_name: str) -> Dict[str, Any]:
	return run_inventory_check(request_name)


def try_start_material_fulfillment(request_name: str) -> Optional[Dict[str, Any]]:
	try:
		return run_inventory_check(request_name)
	except frappe.ValidationError as e:
		_mark_inventory_check_required(request_name, str(e))
		frappe.log_error(title=f"Material Inventory Check could not start for {request_name}")
		return {
			"status": "pending",
			"message": _("Approvals are complete. Inventory Check is still required: {0}").format(str(e)),
		}
	except Exception:
		_mark_inventory_check_required(
			request_name,
			_("Inventory Check could not start. Open the request and run Inventory Check."),
		)
		frappe.log_error(title=f"Material Inventory Check could not start for {request_name}")
		return {
			"status": "pending",
			"message": _("Approvals are complete. Inventory Check is pending and must be completed."),
		}


def _mark_inventory_check_required(request_name: str, remarks: str) -> None:
	doc = frappe.get_doc("Requests", request_name)
	if not is_material_request(doc):
		return
	if doc.status not in ("Approved", "In Progress"):
		return
	init_material_workflow(doc)
	_set_step(doc, STAGE_INVENTORY_CHECK, "Current", remarks=remarks)
	doc.fulfillment_stage = STAGE_INVENTORY_CHECK
	_save(doc)


@frappe.whitelist()
def run_inventory_check(request_name: str) -> Dict[str, Any]:
	_require_erpnext()
	doc = frappe.get_doc("Requests", request_name)
	if not is_material_request(doc):
		frappe.throw(_("This request is not a Material Request"))
	if doc.status not in ("Approved", "In Progress"):
		frappe.throw(_("Inventory Check starts only after all required approvals are completed"))

	init_material_workflow(doc)
	if _status_of(doc, STAGE_INVENTORY_CHECK) == "Done":
		return {
			"status": "success",
			"message": _("Inventory Check already completed"),
			"inventory_check_result": getattr(doc, "inventory_check_result", None),
			"fulfillment_stage": doc.fulfillment_stage,
			"fulfillment_path": doc.fulfillment_path,
			"created_docs": [part.strip() for part in str(doc.execution_docname or "").split(",") if part.strip()],
		}

	items = _material_items(doc)
	if not items:
		frappe.throw(_("Add at least one item before running Inventory Check"))

	company = _company()
	buckets = _allocate_items(doc)
	created: List[str] = []
	if buckets["issue"]:
		name = _create_erp_material_request(doc, company, "Material Issue", buckets["issue"])
		created.append(name)
		_link_document(doc, "Material Request", name, STAGE_ISSUANCE, "Inventory")
		_set_step(doc, STAGE_ISSUANCE, "Pending", "Material Request", name)
	if buckets["transfer"]:
		name = _create_erp_material_request(doc, company, "Material Transfer", buckets["transfer"])
		created.append(name)
		_link_document(doc, "Material Request", name, STAGE_ISSUANCE, "Inventory")
		issuance = _row(doc, STAGE_ISSUANCE)
		if issuance and issuance.document_name:
			issuance.document_name = f"{issuance.document_name}, {name}"
		else:
			_set_step(doc, STAGE_ISSUANCE, "Pending", "Material Request", name)
	if buckets["purchase"]:
		name = _create_erp_material_request(doc, company, "Purchase", buckets["purchase"])
		created.append(name)
		_link_document(doc, "Material Request", name, STAGE_PURCHASE, "Purchase")
		_set_step(doc, STAGE_PURCHASE, "Pending", "Material Request", name)

	if not created:
		frappe.throw(_("No Material Request could be created from the item quantities"))

	has_inventory = bool(buckets["issue"] or buckets["transfer"])
	has_purchase = bool(buckets["purchase"])
	if has_inventory and not has_purchase:
		result = "Available"
		remarks = _("Material is available. The request is proceeding to Internal Transfer / Issuance.")
	elif has_purchase and not has_inventory:
		result = "Not Available"
		remarks = _("Material is not available. The request is proceeding to the Purchase Process.")
	else:
		result = "Partially Available"
		remarks = _(
			"Some material is available. Available quantity proceeds to Internal Transfer / Issuance; "
			"the rest proceeds to the Purchase Process."
		)
	doc.inventory_check_result = result
	_set_step(doc, STAGE_INVENTORY_CHECK, "Done", "Material Request", ", ".join(created), remarks)

	if has_inventory:
		_set_step(doc, STAGE_ISSUANCE, "Current", remarks=_("Material is available in inventory"))
	else:
		_set_step(
			doc,
			STAGE_ISSUANCE,
			"Skipped",
			remarks=_("Material is not available. Skipped Internal Transfer / Issuance."),
		)

	if has_purchase:
		_set_step(
			doc,
			STAGE_PURCHASE,
			"Done",
			remarks=_("Material is not available. Purchase process started."),
		)
		_set_step(doc, STAGE_SUPPLIER_SELECTION, "Current")
	else:
		for stage in PURCHASE_STAGES:
			_set_step(
				doc,
				stage,
				"Skipped",
				remarks=_("Not required. Material is available in inventory."),
			)

	_refresh_stage(doc)
	doc.status = "In Progress"
	_save(doc)
	return {
		"status": "success",
		"message": remarks,
		"inventory_check_result": result,
		"fulfillment_stage": doc.fulfillment_stage,
		"fulfillment_path": doc.fulfillment_path,
		"created_docs": created,
	}


@frappe.whitelist()
def get_material_workflow_action(request_name: str) -> Dict[str, Any]:
	doc = frappe.get_doc("Requests", request_name)
	if not is_material_request(doc) or doc.status not in ("Approved", "In Progress"):
		return {"can_act": False, "stages": []}
	roles = set(frappe.get_roles())
	can_act = frappe.session.user == "Administrator" or bool(roles & {"System Manager", "Execution Team"})
	init_needed = not (doc.material_workflow or [])
	stages = []
	if init_needed or _status_of(doc, STAGE_INVENTORY_CHECK) != "Done":
		if doc.status in ("Approved", "In Progress"):
			stages.append(
				{
					"stage": STAGE_INVENTORY_CHECK,
					"label": ADVANCE_LABELS[STAGE_INVENTORY_CHECK],
					"prompt": None,
				}
			)
	else:
		seen_stages = set()
		for row in doc.material_workflow or []:
			if row.step_status != "Current":
				continue
			stage = STAGE_RFQ if row.stage == STAGE_TENDER else row.stage
			if stage in seen_stages:
				continue
			seen_stages.add(stage)
			stages.append(
				{
					"stage": stage,
					"label": ADVANCE_LABELS.get(stage, stage),
					"prompt": _prompt_for(stage),
				}
			)
	return {
		"can_act": can_act and bool(stages),
		"stages": stages,
		"fulfillment_stage": getattr(doc, "fulfillment_stage", None),
		"tender": getattr(doc, "tender", None),
		"suppliers_editable": can_act and _status_of(doc, STAGE_SUPPLIER_SELECTION) == "Current",
	}


def _prompt_for(stage: str) -> Optional[str]:
	if stage == STAGE_PRICE_DELIVERY:
		return "price_delivery"
	if stage == STAGE_COMPARISON:
		return "comparison"
	return None


@frappe.whitelist()
def advance_material_workflow(
	request_name: str,
	stage: Optional[str] = None,
	tender_notes: Optional[str] = None,
	tender_reference: Optional[str] = None,
	selected_quotation: Optional[str] = None,
	expected_delivery_date: Optional[str] = None,
	comparison_notes: Optional[str] = None,
) -> Dict[str, Any]:
	_require_fulfillment_role()
	_require_erpnext()
	doc = frappe.get_doc("Requests", request_name)
	if not is_material_request(doc):
		frappe.throw(_("This request is not a Material Request"))

	if not (doc.material_workflow or []) or _status_of(doc, STAGE_INVENTORY_CHECK) != "Done":
		return run_inventory_check(request_name)

	current = [row.stage for row in doc.material_workflow if row.step_status == "Current"]
	target = stage or (current[0] if current else None)
	if not target:
		frappe.throw(_("There is no Material Request workflow step to advance"))
	if target == STAGE_RFQ and STAGE_TENDER in current and STAGE_RFQ not in current:
		_set_step(doc, STAGE_TENDER, "Done", "Tender", getattr(doc, "tender", None))
		_set_step(doc, STAGE_RFQ, "Current")
		current = [row.stage for row in doc.material_workflow if row.step_status == "Current"]
	if target not in current and target != STAGE_COMPLETED:
		frappe.throw(_("Stage {0} is not waiting to be advanced").format(target))

	handlers = {
		STAGE_ISSUANCE: _advance_issuance,
		STAGE_PURCHASE: _advance_purchase,
		STAGE_SUPPLIER_SELECTION: _advance_supplier_selection,
		STAGE_TENDER: lambda d: _advance_tender(d, tender_notes, tender_reference),
		STAGE_RFQ: _advance_rfq,
		STAGE_COMPARISON: lambda d: _advance_comparison(d, selected_quotation, expected_delivery_date, comparison_notes),
		STAGE_PRICE_DELIVERY: lambda d: _advance_price_delivery(d, selected_quotation, expected_delivery_date),
		STAGE_PO: _advance_po,
		STAGE_DELIVERY: _advance_delivery,
		STAGE_COMPLETED: _advance_completed,
	}
	handler = handlers.get(target)
	if not handler:
		frappe.throw(_("Stage {0} cannot be advanced").format(target))
	message = handler(doc)
	_maybe_complete(doc)
	_refresh_stage(doc)
	_save(doc)
	return {
		"status": "success",
		"message": message,
		"fulfillment_stage": doc.fulfillment_stage,
		"new_status": doc.status,
		"tender": getattr(doc, "tender", None),
		"rfq": getattr(doc, "rfq", None),
	}


def _docs_for_stage(doc, stage: str) -> List[str]:
	row = _row(doc, stage)
	if not row or not row.document_name:
		return []
	return [name.strip() for name in str(row.document_name).split(",") if name.strip()]


def _submit_if_draft(doctype: str, name: str) -> None:
	if not name or not frappe.db.exists(doctype, name):
		return
	target = frappe.get_doc(doctype, name)
	if target.docstatus == 0:
		target.flags.ignore_permissions = True
		target.submit()


def _insert_mapped(mapped, request_name: Optional[str] = None) -> str:
	stamp_request_link(mapped, request_name)
	if request_name and getattr(mapped, "meta", None) and mapped.meta.has_field("request_center_tender"):
		tender_name = frappe.db.get_value("Requests", request_name, "tender")
		if tender_name:
			mapped.set("request_center_tender", tender_name)
	mapped.flags.ignore_permissions = True
	mapped.insert(ignore_permissions=True)
	return mapped.name


def _advance_issuance(doc) -> str:
	created = []
	notes = []
	for name in _docs_for_stage(doc, STAGE_ISSUANCE):
		_submit_if_draft("Material Request", name)
		purpose = frappe.db.get_value("Material Request", name, "material_request_type")
		from erpnext.stock.doctype.material_request.material_request import make_stock_entry

		try:
			entry = make_stock_entry(name)
			entry_name = _insert_mapped(entry, doc.name)
		except Exception as exc:
			frappe.throw(
				_("Could not create a Stock Entry from Material Request {0}: {1}").format(name, str(exc))
			)
		created.append(entry_name)
		_link_document(doc, "Stock Entry", entry_name, STAGE_ISSUANCE, "Inventory")
		kind = _("Internal Transfer") if purpose == "Material Transfer" else _("Issuance")
		notes.append(_("Stock Entry {0} created for {1}").format(entry_name, kind))
	_set_step(
		doc,
		STAGE_ISSUANCE,
		"Done",
		"Stock Entry",
		", ".join(created) if created else None,
		"; ".join(notes) if notes else _("Issuance / transfer documents created"),
	)
	return _("Internal Transfer / Issuance completed")


def _advance_purchase(doc) -> str:
	for name in _docs_for_stage(doc, STAGE_PURCHASE):
		_submit_if_draft("Material Request", name)
	_set_step(doc, STAGE_PURCHASE, "Done", remarks=_("Purchase path started"))
	_set_step(doc, STAGE_SUPPLIER_SELECTION, "Current")
	return _("Purchase started. Create the Tender, add suppliers there, then send the RFQ from this request.")


def _advance_supplier_selection(doc) -> str:
	from request_center.tender import copy_suppliers_to_request, ensure_tender_for_request

	tender = ensure_tender_for_request(
		doc,
		notes=getattr(doc, "tender_notes", None),
		external_reference=getattr(doc, "tender_reference", None),
	)
	doc.tender = tender.name
	copy_suppliers_to_request(tender)
	doc.reload()
	doc.tender = tender.name
	suppliers = [row.supplier for row in (doc.material_suppliers or []) if row.supplier]
	if not suppliers:
		suppliers = [row.supplier for row in (tender.suppliers or []) if row.supplier]
		for supplier in suppliers:
			doc.append("material_suppliers", {"supplier": supplier})
	if suppliers:
		remarks = _("Suppliers: {0}").format(", ".join(suppliers))
	else:
		remarks = _("Tender created. Add suppliers on the Tender, then Save.")
	_set_step(doc, STAGE_SUPPLIER_SELECTION, "Done", remarks=remarks)
	_link_document(doc, "Tender", tender.name, STAGE_TENDER, "Purchase")
	_set_step(doc, STAGE_TENDER, "Current", "Tender", tender.name)
	return _("Tender {0} created. Add suppliers on the Tender and Save, then Create and Send RFQ from this request.").format(
		tender.name
	)


def _advance_tender(doc, tender_notes: Optional[str], tender_reference: Optional[str] = None) -> str:
	if tender_notes:
		doc.tender_notes = tender_notes
	if tender_reference:
		doc.tender_reference = tender_reference
	from request_center.tender import ensure_tender_for_request

	tender = ensure_tender_for_request(doc, notes=tender_notes, external_reference=tender_reference)
	if tender.status == "Draft":
		tender.status = "Open"
		tender.flags.ignore_permissions = True
		tender.save()
	doc.tender = tender.name
	_link_document(doc, "Tender", tender.name, STAGE_TENDER, "Purchase")
	remarks = _("Tender {0}").format(tender.name)
	if tender.external_reference:
		remarks += " — " + tender.external_reference
	_set_step(doc, STAGE_TENDER, "Done", "Tender", tender.name, remarks)
	_set_step(doc, STAGE_RFQ, "Current")
	return _("Tender {0} is ready. Create and send the RFQ to the selected suppliers.").format(tender.name)


def _advance_rfq(doc) -> str:
	from request_center.rfq import create_and_send_rfq_for_request

	result = create_and_send_rfq_for_request(doc)
	rfq_name = result["rfq"]
	_link_document(doc, "Request for Quotation", rfq_name, STAGE_RFQ, "Purchase")
	for quotation in result.get("drafts") or []:
		_link_document(doc, "Supplier Quotation", quotation, STAGE_RFQ, "Purchase")
	_set_step(doc, STAGE_RFQ, "Done", "Request for Quotation", rfq_name, result["message"])
	_set_step(doc, STAGE_COMPARISON, "Current", "Request for Quotation", rfq_name)
	return result["message"]


def _quotations_for_rfq(rfq_name: str) -> List[Dict[str, Any]]:
	if not rfq_name:
		return []
	names = frappe.get_all(
		"Supplier Quotation Item",
		filters={"request_for_quotation": rfq_name},
		pluck="parent",
	)
	if not names:
		return []
	return frappe.get_all(
		"Supplier Quotation",
		filters={"name": ["in", list(set(names))], "docstatus": 1},
		fields=["name", "supplier", "grand_total", "valid_till"],
		order_by="grand_total asc",
	)


def _advance_comparison(
	doc,
	selected_quotation: Optional[str],
	expected_delivery_date: Optional[str] = None,
	comparison_notes: Optional[str] = None,
) -> str:
	from request_center.supplier_comparison import apply_comparison_to_request, build_comparison_rows

	comparison = build_comparison_rows(doc)
	rows = comparison["rows"]
	if not rows:
		rfq_name = comparison.get("rfq") or (_docs_for_stage(doc, STAGE_RFQ) or ["the RFQ"])[0]
		frappe.throw(
			_("Submit at least one Supplier Quotation against RFQ {0} before comparison").format(rfq_name)
		)
	if not selected_quotation:
		frappe.throw(_("Compare Price and Delivery Time, then select a supplier"))
	chosen = next((row for row in rows if row["supplier_quotation"] == selected_quotation), None)
	if not chosen:
		frappe.throw(_("Supplier Quotation {0} is not a submitted quote for this RFQ").format(selected_quotation))
	if comparison_notes:
		doc.comparison_notes = comparison_notes
	doc.selected_quotation = chosen["supplier_quotation"]
	doc.awarded_supplier = chosen["supplier"]
	if expected_delivery_date:
		doc.expected_delivery_date = expected_delivery_date
	elif chosen.get("delivery_date"):
		doc.expected_delivery_date = chosen["delivery_date"]
	elif not doc.expected_delivery_date:
		doc.expected_delivery_date = nowdate()
	apply_comparison_to_request(doc, chosen["supplier_quotation"])
	_link_document(doc, "Supplier Quotation", chosen["supplier_quotation"], STAGE_COMPARISON, "Purchase")
	for row in rows:
		_link_document(doc, "Supplier Quotation", row["supplier_quotation"], STAGE_COMPARISON, "Purchase")
	lines = [
		_("{0}: {1}, {2}").format(row["supplier_name"] or row["supplier"], row["price_display"], row["delivery_time"])
		for row in rows
	]
	_set_step(
		doc,
		STAGE_COMPARISON,
		"Done",
		"Supplier Quotation",
		chosen["supplier_quotation"],
		_("Selected {0} after comparing Price and Delivery Time. Offers: {1}").format(
			chosen["supplier"], "; ".join(lines)
		),
	)
	_set_step(
		doc,
		STAGE_PRICE_DELIVERY,
		"Done",
		"Supplier Quotation",
		chosen["supplier_quotation"],
		_("Price {0}, delivery {1}").format(chosen["price_display"], doc.expected_delivery_date),
	)
	_set_step(doc, STAGE_PO, "Current", "Supplier Quotation", chosen["supplier_quotation"])
	from request_center.tender import record_tender_award, sync_tender_offers

	record_tender_award(doc, chosen["supplier_quotation"], chosen["supplier"])
	if getattr(doc, "tender", None):
		sync_tender_offers(doc.tender)
	return _("Supplier Comparison complete. Awarded {0} at {1} / {2}.").format(
		chosen["supplier"], chosen["price_display"], chosen["delivery_time"]
	)


def _advance_price_delivery(doc, selected_quotation: Optional[str], expected_delivery_date: Optional[str]) -> str:
	quotation = selected_quotation or doc.selected_quotation
	if not quotation:
		frappe.throw(_("Select the awarded Supplier Quotation"))
	if not frappe.db.exists("Supplier Quotation", quotation):
		frappe.throw(_("Supplier Quotation {0} does not exist").format(quotation))
	sq = frappe.get_doc("Supplier Quotation", quotation)
	doc.selected_quotation = quotation
	doc.awarded_supplier = sq.supplier
	dates = [getdate(row.expected_delivery_date) for row in sq.items if getattr(row, "expected_delivery_date", None)]
	doc.expected_delivery_date = expected_delivery_date or (min(dates) if dates else None) or nowdate()
	_set_step(
		doc,
		STAGE_PRICE_DELIVERY,
		"Done",
		"Supplier Quotation",
		quotation,
		_("Price {0}, delivery {1}").format(flt(sq.grand_total), doc.expected_delivery_date),
	)
	_set_step(doc, STAGE_PO, "Current", "Supplier Quotation", quotation)
	return _("Price and delivery confirmed")


def _advance_po(doc) -> str:
	from request_center.purchase_order import create_purchase_order_for_request

	result = create_purchase_order_for_request(doc)
	po_name = result["purchase_order"]
	_link_document(doc, "Purchase Order", po_name, STAGE_PO, "Purchase")
	_set_step(doc, STAGE_PO, "Done", "Purchase Order", po_name, result["message"])
	_set_step(doc, STAGE_DELIVERY, "Current", "Purchase Order", po_name)
	return result["message"]


def _advance_delivery(doc) -> str:
	po_name = (_docs_for_stage(doc, STAGE_PO) or [None])[0]
	if not po_name:
		frappe.throw(_("Create a Purchase Order before recording delivery"))
	_submit_if_draft("Purchase Order", po_name)
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	pr = make_purchase_receipt(po_name)
	pr_name = _insert_mapped(pr, doc.name)
	_link_document(doc, "Purchase Receipt", pr_name, STAGE_DELIVERY, "Purchase")
	_set_step(doc, STAGE_DELIVERY, "Done", "Purchase Receipt", pr_name)
	return _("Delivery recorded as Purchase Receipt {0}").format(pr_name)


def _advance_completed(doc) -> str:
	doc.status = "Completed"
	_set_step(doc, STAGE_COMPLETED, "Done")
	doc.fulfillment_stage = STAGE_COMPLETED
	return _("Material Request completed")


def _maybe_complete(doc) -> None:
	issuance_done = _status_of(doc, STAGE_ISSUANCE) in ("Done", "Skipped")
	delivery_done = _status_of(doc, STAGE_DELIVERY) in ("Done", "Skipped")
	if not (issuance_done and delivery_done):
		return
	_set_step(doc, STAGE_COMPLETED, "Current")
	_advance_completed(doc)


def material_workflow_complete(doc) -> bool:
	if not is_material_request(doc):
		return True
	if not (doc.material_workflow or []):
		return False
	return _status_of(doc, STAGE_COMPLETED) == "Done"
