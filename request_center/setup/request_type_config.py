import frappe


def migrate_approval_levels_onto_request_types() -> None:
	if not frappe.db.table_exists("Request Type"):
		return
	if not frappe.db.exists("DocType", "Request Type Approval Level"):
		return
	meta = frappe.get_meta("Request Type")
	if not meta.has_field("approval_levels"):
		return

	_copy_legacy_role_rows_to_employee_levels()

	for name in frappe.get_all("Request Type", pluck="name"):
		doc = frappe.get_doc("Request Type", name)
		if doc.get("approval_levels"):
			continue
		doc._copy_legacy_approval_matrix()
		if doc.get("approval_levels"):
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)

	frappe.db.commit()


def _copy_legacy_role_rows_to_employee_levels() -> None:
	if not frappe.db.table_exists("Approval Matrix Level"):
		return
	if not frappe.db.table_exists("Request Type Approval Level"):
		return

	from request_center.request_center.doctype.request_type.request_type import (
		_employee_for_matrix_row,
	)

	old_rows = frappe.db.sql(
		"""
		SELECT parent, level, based_on, criteria, approver_role, fallback_role
		FROM `tabApproval Matrix Level`
		WHERE parenttype = 'Request Type' AND parentfield = 'approval_levels'
		ORDER BY parent, level
		""",
		as_dict=True,
	)
	if not old_rows:
		return

	by_parent: dict[str, list] = {}
	for row in old_rows:
		by_parent.setdefault(row.parent, []).append(row)

	for parent, rows in by_parent.items():
		if not frappe.db.exists("Request Type", parent):
			continue
		if frappe.db.exists(
			"Request Type Approval Level",
			{"parent": parent, "parenttype": "Request Type"},
		):
			continue
		doc = frappe.get_doc("Request Type", parent)
		for row in rows:
			employee = _employee_for_matrix_row(doc, row)
			if not employee:
				continue
			doc.append(
				"approval_levels",
				{
					"level": row.level,
					"approver": employee,
					"required": 1,
				},
			)
		if doc.get("approval_levels"):
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)


def migrate_request_approval_workflow() -> None:
	for state_name, style in (
		("Pending Approval", "Warning"),
		("Need Approval", "Warning"),
	):
		if not frappe.db.exists("Workflow State", state_name):
			frappe.get_doc(
				{
					"doctype": "Workflow State",
					"workflow_state_name": state_name,
					"style": style,
				}
			).insert(ignore_permissions=True)

	if not frappe.db.table_exists("Requests"):
		frappe.db.commit()
		return

	if frappe.db.has_column("Requests", "status"):
		frappe.db.sql(
			"""
			UPDATE `tabRequests`
			SET status = 'Need Approval'
			WHERE status IN ('Pending Approval', 'Pending Manager', 'Pending Department')
			"""
		)

	from request_center.api.requests import apply_approval_progress_to_doc

	names = frappe.get_all("Requests", pluck="name")
	for name in names:
		try:
			doc = frappe.get_doc("Requests", name)
			apply_approval_progress_to_doc(doc)
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Approval tracking migrate failed for {name}")

	frappe.db.commit()
