# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import get_url_to_form

PENDING_STATUSES = (
	"Need Approval",
	"Pending Approval",
	"Pending Manager",
	"Pending Department",
)


def notify_request_change(
	doc,
	previous: Any = None,
	old_status: Optional[str] = None,
	old_level: Optional[str] = None,
) -> None:
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
		return
	if getattr(doc.flags, "request_center_notified", False):
		return

	if previous is not None:
		old_status = old_status or previous.get("status")
		old_level = old_level if old_level is not None else previous.get("current_approval_level")

	new_status = getattr(doc, "status", None)
	new_level = getattr(doc, "current_approval_level", None)
	if old_status in (None, "", "Draft") and new_status in (None, "", "Draft"):
		return
	if old_status == new_status and _same_level(old_level, new_level):
		old_stage = previous.get("fulfillment_stage") if previous is not None else None
		new_stage = getattr(doc, "fulfillment_stage", None)
		if str(old_stage or "") == str(new_stage or ""):
			return
		if new_status == "In Progress" and new_stage:
			doc.flags.request_center_notified = True
			link = _request_link(doc)
			_notify_requester(
				doc,
				_("Request {0} moved to {1}").format(doc.name, new_stage),
				_("Request {0} is now at {1}.").format(link, frappe.utils.escape_html(str(new_stage))),
			)
		return

	doc.flags.request_center_notified = True
	summary = getattr(doc, "approval_status_summary", None) or new_status or ""
	link = _request_link(doc)

	if new_status in PENDING_STATUSES and old_status in (None, "", "Draft"):
		_notify_requester(
			doc,
			_("Request {0} submitted").format(doc.name),
			_("Your request {0} has been submitted and is now waiting for approval. {1}").format(
				link, frappe.utils.escape_html(summary)
			),
		)
		_notify_current_approver(doc, link)
		return

	if new_status in PENDING_STATUSES and old_status in PENDING_STATUSES and not _same_level(old_level, new_level):
		_notify_requester(
			doc,
			_("Request {0} moved to the next approval level").format(doc.name),
			_("Request {0} moved to the next approval level. {1}").format(
				link, frappe.utils.escape_html(summary)
			),
		)
		_notify_current_approver(doc, link)
		return

	if new_status == "Approved" and old_status != "Approved":
		_notify_requester(
			doc,
			_("Request {0} approved").format(doc.name),
			_("Request {0} has been approved.").format(link),
		)
		return

	if new_status == "Rejected" and old_status != "Rejected":
		reason = getattr(doc, "reject_reason", None)
		body = _("Request {0} has been rejected.").format(link)
		if reason:
			body += "<br>" + _("Reason: {0}").format(frappe.utils.escape_html(reason))
		_notify_requester(doc, _("Request {0} rejected").format(doc.name), body)
		return

	if new_status == "Completed" and old_status != "Completed":
		_notify_requester(
			doc,
			_("Request {0} completed").format(doc.name),
			_("Request {0} has been completed.").format(link),
		)
		return

	if new_status == "In Progress" and old_status != "In Progress":
		path = getattr(doc, "fulfillment_path", None)
		stage = getattr(doc, "fulfillment_stage", None)
		body = _("Request {0} is now in progress.").format(link)
		result = getattr(doc, "inventory_check_result", None)
		if result == "Available":
			body += " " + _("Inventory Check: material is available. The request is proceeding to Internal Transfer / Issuance.")
		elif result == "Not Available":
			body += " " + _("Inventory Check: material is not available. The request is proceeding to the Purchase Process.")
		elif result == "Partially Available":
			body += " " + _(
				"Inventory Check: some material is available. Available quantity proceeds to Internal Transfer / Issuance; the rest proceeds to Purchase."
			)
		elif stage:
			body += " " + _("Stage: {0}.").format(frappe.utils.escape_html(stage))
		elif path:
			body += " " + _("Fulfillment: {0}.").format(frappe.utils.escape_html(path))
		_notify_requester(
			doc,
			_("Request {0} in progress").format(doc.name),
			body,
		)
		return

	if new_status != old_status:
		_notify_requester(
			doc,
			_("Request {0} status changed").format(doc.name),
			_("Request {0} is now {1}.").format(link, frappe.utils.escape_html(new_status or "")),
		)


def _same_level(left: Optional[str], right: Optional[str]) -> bool:
	return str(left or "") == str(right or "")


def _request_link(doc) -> str:
	url = get_url_to_form("Requests", doc.name)
	return f'<a href="{url}">{frappe.utils.escape_html(doc.name)}</a>'


def _notify_current_approver(doc, link: str) -> None:
	level = getattr(doc, "current_approval_level", None) or ""
	approver_name = getattr(doc, "current_approver", None) or ""
	subject = _("Approval required for {0}").format(doc.name)
	body = _("Request {0} requires your approval at Level {1}.").format(
		link, frappe.utils.escape_html(str(level))
	)
	if approver_name:
		body += " " + _("Approver: {0}.").format(frappe.utils.escape_html(approver_name))
	_notify_users([getattr(doc, "current_approver_user", None)], subject, body, doc)


def _notify_requester(doc, subject: str, body: str) -> None:
	_notify_users([getattr(doc, "requested_by", None), getattr(doc, "owner", None)], subject, body, doc)


def _notify_users(users: list[Optional[str]], subject: str, body: str, doc) -> None:
	from frappe.desk.doctype.notification_settings.notification_settings import (
		is_notifications_enabled,
	)

	seen: set[str] = set()
	for user in users:
		if not user or user in seen or user == "Guest":
			continue
		if not frappe.db.exists("User", user):
			continue
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		if not is_notifications_enabled(user):
			continue
		seen.add(user)
		try:
			log = frappe.new_doc("Notification Log")
			log.type = "Alert"
			log.document_type = "Requests"
			log.document_name = doc.name
			log.subject = subject
			log.email_content = body
			log.from_user = frappe.session.user
			log.for_user = user
			log.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Request notification failed for {user}")
		_email_user(user, subject, body, doc)


def _email_user(user: str, subject: str, body: str, doc) -> None:
	email = frappe.db.get_value("User", user, "email")
	if not email:
		return
	try:
		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=body,
			now=False,
			reference_doctype="Requests",
			reference_name=doc.name,
		)
	except Exception:
		frappe.log_error(title=f"Request email notification failed for {user}")
