# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, nowdate

METHOD_MANUAL = "Manual Comparison"
METHOD_SCORE = "Weighted Score"
METHOD_RANK = "Ranked Criteria"
CRITERION_PRICE = "Price"
CRITERION_DELIVERY = "Delivery Time"

DEFAULT_POLICY = {
	"comparison_method": METHOD_SCORE,
	"price_weight": 50.0,
	"delivery_weight": 50.0,
	"rank_primary": CRITERION_PRICE,
}

UNSPECIFIED_DAYS = 10_000


def get_comparison_policy(request_doc) -> Dict[str, Any]:
	policy = dict(DEFAULT_POLICY)
	request_type = getattr(request_doc, "request_type", None)
	if request_type and frappe.db.exists("Request Type", request_type):
		rt = frappe.get_cached_doc("Request Type", request_type)
		if getattr(rt, "comparison_method", None):
			policy["comparison_method"] = rt.comparison_method
		if rt.meta.has_field("price_weight") and rt.price_weight is not None:
			policy["price_weight"] = flt(rt.price_weight)
		if rt.meta.has_field("delivery_weight") and rt.delivery_weight is not None:
			policy["delivery_weight"] = flt(rt.delivery_weight)
		if getattr(rt, "rank_primary", None):
			policy["rank_primary"] = rt.rank_primary
	price_weight = max(flt(policy["price_weight"]), 0)
	delivery_weight = max(flt(policy["delivery_weight"]), 0)
	total = price_weight + delivery_weight
	if total <= 0:
		price_weight, delivery_weight = 50.0, 50.0
	elif abs(total - 100) > 0.05:
		price_weight = price_weight * 100 / total
		delivery_weight = delivery_weight * 100 / total
	policy["price_weight"] = price_weight
	policy["delivery_weight"] = delivery_weight
	if policy["rank_primary"] not in (CRITERION_PRICE, CRITERION_DELIVERY):
		policy["rank_primary"] = CRITERION_PRICE
	if policy["comparison_method"] not in (METHOD_MANUAL, METHOD_SCORE, METHOD_RANK):
		policy["comparison_method"] = METHOD_SCORE
	return policy


def policy_summary(policy: Dict[str, Any]) -> str:
	method = policy["comparison_method"]
	if method == METHOD_SCORE:
		return _(
			"Weighted Score: Price {0}% + Delivery Time {1}%. Rank 1 is recommended; the purchasing team still confirms the supplier."
		).format(cint(round(policy["price_weight"])), cint(round(policy["delivery_weight"])))
	if method == METHOD_RANK:
		secondary = CRITERION_DELIVERY if policy["rank_primary"] == CRITERION_PRICE else CRITERION_PRICE
		return _(
			"Ranked Criteria: suppliers are ordered by {0}, then {1}. Rank 1 is recommended; the purchasing team still confirms the supplier."
		).format(policy["rank_primary"], secondary)
	return _(
		"Manual Comparison: Price and Delivery Time are shown for every supplier. Select according to the company's purchasing policy."
	)


def _rfq_name(request_doc) -> Optional[str]:
	from request_center.rfq import _existing_rfq

	return _existing_rfq(request_doc)


def _quotations_for_request(request_doc) -> List[Dict[str, Any]]:
	rfq_name = _rfq_name(request_doc)
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
		fields=["name", "supplier", "supplier_name", "grand_total", "currency", "transaction_date", "valid_till"],
	)


def _delivery_for_quotation(quote) -> Dict[str, Any]:
	items = frappe.get_all(
		"Supplier Quotation Item",
		filters={"parent": quote.name},
		fields=["expected_delivery_date"],
	)
	dates = [getdate(row.expected_delivery_date) for row in items if row.expected_delivery_date]
	delivery_date = max(dates) if dates else None
	base = getdate(quote.transaction_date) if quote.transaction_date else getdate(nowdate())
	delivery_days = date_diff(delivery_date, base) if delivery_date else None
	if delivery_days is not None and delivery_days < 0:
		delivery_days = 0
	if delivery_days is None:
		delivery_time = _("Not specified")
	elif delivery_days == 1:
		delivery_time = _("1 Day")
	else:
		delivery_time = _("{0} Days").format(cint(delivery_days))
	return {
		"delivery_date": delivery_date,
		"delivery_days": delivery_days,
		"delivery_time": delivery_time,
	}


def _price_display(amount: float, currency: Optional[str]) -> str:
	return frappe.format_value(flt(amount), {"fieldtype": "Currency", "options": currency or ""})


def build_comparison_rows(request_doc) -> Dict[str, Any]:
	policy = get_comparison_policy(request_doc)
	quotes = _quotations_for_request(request_doc)
	rows: List[Dict[str, Any]] = []
	for quote in quotes:
		delivery = _delivery_for_quotation(quote)
		price = flt(quote.grand_total)
		rows.append(
			{
				"supplier": quote.supplier,
				"supplier_name": quote.supplier_name or quote.supplier,
				"supplier_quotation": quote.name,
				"price": price,
				"currency": quote.currency,
				"price_display": _price_display(price, quote.currency),
				"delivery_date": delivery["delivery_date"],
				"delivery_days": delivery["delivery_days"],
				"delivery_time": delivery["delivery_time"],
				"price_score": 0.0,
				"delivery_score": 0.0,
				"total_score": 0.0,
				"rank": 0,
				"recommended": 0,
				"selected": 0,
			}
		)
	_score_rows(rows, policy)
	_rank_rows(rows, policy)
	recommended = next((row["supplier_quotation"] for row in rows if row["recommended"]), None)
	return {
		"policy": policy,
		"policy_summary": policy_summary(policy),
		"rfq": _rfq_name(request_doc),
		"rows": rows,
		"recommended_quotation": recommended,
		"recommended_supplier": next((row["supplier"] for row in rows if row["recommended"]), None),
	}


def _score_rows(rows: List[Dict[str, Any]], policy: Dict[str, Any]) -> None:
	priced = [row for row in rows if flt(row["price"]) > 0]
	min_price = min((flt(row["price"]) for row in priced), default=0)
	dated = [row for row in rows if row["delivery_days"] is not None]
	min_days = min((max(cint(row["delivery_days"]), 1) for row in dated), default=1)
	price_weight = flt(policy["price_weight"]) / 100.0
	delivery_weight = flt(policy["delivery_weight"]) / 100.0
	for row in rows:
		price = flt(row["price"])
		row["price_score"] = round(100.0 * min_price / price, 2) if price > 0 and min_price > 0 else 0.0
		if row["delivery_days"] is None:
			row["delivery_score"] = 0.0
		else:
			days = max(cint(row["delivery_days"]), 1)
			row["delivery_score"] = round(100.0 * min_days / days, 2)
		row["total_score"] = round(row["price_score"] * price_weight + row["delivery_score"] * delivery_weight, 2)


def _sort_key(row: Dict[str, Any], policy: Dict[str, Any]):
	days = row["delivery_days"] if row["delivery_days"] is not None else UNSPECIFIED_DAYS
	price = flt(row["price"])
	score = flt(row["total_score"])
	method = policy["comparison_method"]
	if method == METHOD_RANK:
		if policy["rank_primary"] == CRITERION_DELIVERY:
			return (days, price, -score, row["supplier_quotation"])
		return (price, days, -score, row["supplier_quotation"])
	return (-score, price, days, row["supplier_quotation"])


def _rank_rows(rows: List[Dict[str, Any]], policy: Dict[str, Any]) -> None:
	ordered = sorted(rows, key=lambda row: _sort_key(row, policy))
	for index, row in enumerate(ordered, start=1):
		row["rank"] = index
		row["recommended"] = 1 if index == 1 else 0
	rows.sort(key=lambda row: row["rank"] or UNSPECIFIED_DAYS)


def apply_comparison_to_request(request_doc, selected_quotation: Optional[str] = None) -> Dict[str, Any]:
	comparison = build_comparison_rows(request_doc)
	request_doc.comparison_method = comparison["policy"]["comparison_method"]
	request_doc.recommended_quotation = comparison["recommended_quotation"]
	request_doc.set("supplier_comparison", [])
	for row in comparison["rows"]:
		request_doc.append(
			"supplier_comparison",
			{
				"rank": row["rank"],
				"supplier": row["supplier"],
				"supplier_name": row["supplier_name"],
				"price": row["price"],
				"currency": row["currency"],
				"delivery_time": row["delivery_time"],
				"delivery_date": row["delivery_date"],
				"delivery_days": row["delivery_days"],
				"price_score": row["price_score"],
				"delivery_score": row["delivery_score"],
				"total_score": row["total_score"],
				"recommended": row["recommended"],
				"selected": 1 if selected_quotation and row["supplier_quotation"] == selected_quotation else 0,
				"supplier_quotation": row["supplier_quotation"],
			},
		)
	return comparison


@frappe.whitelist()
def get_supplier_comparison(request_name: str) -> Dict[str, Any]:
	if not request_name:
		frappe.throw(_("Request is required"))
	doc = frappe.get_doc("Requests", request_name)
	if getattr(doc, "category", None) != "Material Request":
		frappe.throw(_("Supplier Comparison is only used on Material Requests"))
	comparison = build_comparison_rows(doc)
	return {
		"status": "success",
		"rfq": comparison["rfq"],
		"comparison_method": comparison["policy"]["comparison_method"],
		"price_weight": comparison["policy"]["price_weight"],
		"delivery_weight": comparison["policy"]["delivery_weight"],
		"rank_primary": comparison["policy"]["rank_primary"],
		"policy_summary": comparison["policy_summary"],
		"rows": comparison["rows"],
		"recommended_quotation": comparison["recommended_quotation"],
		"recommended_supplier": comparison["recommended_supplier"],
		"selected_quotation": getattr(doc, "selected_quotation", None),
	}
