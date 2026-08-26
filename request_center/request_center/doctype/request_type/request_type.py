# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
import re


class RequestType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from request_center.request_center.doctype.request_type_approval_level.request_type_approval_level import RequestTypeApprovalLevel
		from request_center.request_center.doctype.request_type_requirement.request_type_requirement import RequestTypeRequirement

		department: DF.Link
		department_manager: DF.Link | None
		approval_matrix: DF.Link | None
		category: DF.Literal["Service Request", "Material Request", "Disbursement Request", "Other Requests"]
		execution_mode: DF.Link | None
		icon: DF.Icon | None
		approval_levels: DF.Table[RequestTypeApprovalLevel]
		comparison_method: DF.Literal["Manual Comparison", "Weighted Score", "Ranked Criteria"] | None
		delivery_weight: DF.Percent
		is_active: DF.Check
		price_weight: DF.Percent
		rank_primary: DF.Literal["Price", "Delivery Time"] | None
		request_type_name: DF.Data
		requirements: DF.Table[RequestTypeRequirement]
	# end: auto-generated types

	def before_validate(self):
		self._ensure_requirement_keys()
		self._normalize_approval_levels()
		self._normalize_purchasing_policy()

	def validate(self):
		from request_center.setup.request_categories import validate_request_category_name

		if not self.category:
			frappe.throw(_("Each Request Type must belong to a Request Category"))
		validate_request_category_name(self.category)
		self._copy_legacy_approval_matrix()
		self._validate_approval_levels()
		self._validate_purchasing_policy()
		self._validate_unique_name()
		if self.is_active and not self.approval_levels:
			frappe.throw(_("Set Approval Levels on this Request Type before making it active"))

	def before_save(self):
		self._copy_legacy_approval_matrix()

	def _validate_unique_name(self):
		if not self.request_type_name:
			return
		exists = frappe.db.exists(
			"Request Type",
			{"request_type_name": self.request_type_name, "name": ["!=", self.name]},
		)
		if exists:
			frappe.throw(_("Request Type Name must be unique"))

	def _copy_legacy_approval_matrix(self):
		if self.approval_levels or not self.approval_matrix:
			return
		if not frappe.db.exists("Approval Matrix", self.approval_matrix):
			return
		matrix = frappe.get_doc("Approval Matrix", self.approval_matrix)
		for row in matrix.approval_levels or []:
			employee = _employee_for_matrix_row(self, row)
			if not employee:
				continue
			self.append(
				"approval_levels",
				{
					"level": row.level,
					"approver": employee,
					"required": 1,
				},
			)

	def _normalize_approval_levels(self):
		for index, row in enumerate(self.approval_levels or [], start=1):
			if not row.level:
				row.level = index
			if row.required is None:
				row.required = 1

	def _validate_approval_levels(self):
		seen = set()
		for row in self.approval_levels or []:
			if row.level in seen:
				frappe.throw(_("Approval Level {0} is used more than once").format(row.level))
			seen.add(row.level)
			if not row.approver:
				frappe.throw(_("Choose an Approver for Level {0}").format(row.level))
			user_id = frappe.db.get_value("Employee", row.approver, "user_id")
			if not user_id:
				frappe.throw(
					_("Approver {0} must be linked to a User so they can approve requests").format(
						row.approver
					)
				)
		if self.is_active:
			required = [row for row in (self.approval_levels or []) if row.required]
			if self.approval_levels and not required:
				frappe.throw(_("At least one Approval Level must be Required on an active Request Type"))

	def _normalize_purchasing_policy(self):
		if self.category != "Material Request":
			return
		from frappe.utils import flt

		if not self.comparison_method:
			self.comparison_method = "Weighted Score"
		if not self.rank_primary:
			self.rank_primary = "Price"
		if flt(self.price_weight) == 0 and flt(self.delivery_weight) == 0:
			self.price_weight = 50
			self.delivery_weight = 50

	def _validate_purchasing_policy(self):
		if self.category != "Material Request":
			return
		from frappe.utils import flt

		if self.comparison_method not in ("Manual Comparison", "Weighted Score", "Ranked Criteria"):
			frappe.throw(_("Choose a Supplier Comparison Method"))
		if self.comparison_method != "Weighted Score":
			return
		price_weight = flt(self.price_weight)
		delivery_weight = flt(self.delivery_weight)
		if price_weight < 0 or delivery_weight < 0:
			frappe.throw(_("Price Weight and Delivery Time Weight cannot be negative"))
		if abs(price_weight + delivery_weight - 100) > 0.05:
			frappe.throw(_("Price Weight and Delivery Time Weight must add up to 100"))

	def _ensure_requirement_keys(self):
		used = set()
		for index, row in enumerate(self.requirements or [], start=1):
			if not row.sort_order:
				row.sort_order = index
			key = (row.field_key or "").strip() or _field_key_from_name(row.field_label)
			base = key
			suffix = 2
			while key in used:
				key = f"{base}_{suffix}"
				suffix += 1
			row.field_key = key
			used.add(key)

	def on_trash(self):
		if frappe.db.exists("Requests", {"request_type": self.name}):
			frappe.throw(
				_("Cannot delete Request Type {0} because existing requests use it. Deactivate it instead.").format(
					self.name
				)
			)


def _field_key_from_name(field_name: str) -> str:
	key = re.sub(r"[^a-z0-9]+", "_", (field_name or "").strip().lower()).strip("_")
	return key or "field"


def _employee_for_user(user: str | None) -> str | None:
	if not user:
		return None
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def _employee_for_matrix_row(request_type, row) -> str | None:
	role = getattr(row, "approver_role", None) or getattr(row, "fallback_role", None)
	if role == "Department Manager" and getattr(request_type, "department_manager", None):
		employee = _employee_for_user(request_type.department_manager)
		if employee:
			return employee
	if not role:
		return None
	users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		pluck="parent",
	)
	for user in users:
		employee = _employee_for_user(user)
		if employee:
			return employee
	return None
