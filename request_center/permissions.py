# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Optional

import frappe


BROAD_REQUEST_ROLES = {
	"System Manager",
	"Department Manager",
	"Department Head",
	"Execution Team",
}


def _can_see_request(doc: Any, user: str) -> bool:
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	if roles & BROAD_REQUEST_ROLES:
		return True
	if getattr(doc, "owner", None) == user:
		return True
	if getattr(doc, "requested_by", None) == user:
		return True
	if getattr(doc, "current_approver_user", None) == user:
		return True
	return False


def has_request_permission(doc: Any, ptype: str = "read", user: Optional[str] = None, **kwargs) -> bool:
	user = user or frappe.session.user
	if ptype != "read":
		return True
	return _can_see_request(doc, user)


def get_request_permission_query_conditions(user: Optional[str] = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator":
		return ""
	if set(frappe.get_roles(user)) & BROAD_REQUEST_ROLES:
		return ""
	user_sql = frappe.db.escape(user)
	return (
		f"(`tabRequests`.owner = {user_sql}"
		f" OR `tabRequests`.requested_by = {user_sql}"
		f" OR `tabRequests`.current_approver_user = {user_sql})"
	)
