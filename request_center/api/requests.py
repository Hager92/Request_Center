from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from datetime import datetime
from typing import Optional, Dict, List, Any
from frappe.utils import strip_html

# =============================================================================
# HELPER: Role lookup
# =============================================================================
def get_users_with_role(role_name: str) -> List[str]:
    users: List[str] = []

    try:
        all_users = frappe.get_all("User", fields=["name"])

        for user in all_users:
            user_doc = frappe.get_doc("User", user.name)
            for user_role in user_doc.roles:
                if user_role.role == role_name:
                    users.append(user.name)
                    break
    except Exception as e:
        frappe.log_error(f"Error getting users with role {role_name}: {str(e)}")

    return users


# =============================================================================
# WHITELISTED API: Approval matrix / approvers
# =============================================================================
@frappe.whitelist()
def get_approvers(request_name: str) -> Dict[int, List[str]]:
    doc = frappe.get_doc("Requests", request_name)

    if not doc.request_type:
        return {}

    approvers: Dict[int, List[str]] = {}

    matrices = frappe.get_all(
        "Approval Matrix",
        filters={"is_active": 1},
        fields=["name"]
    )

    for matrix in matrices:
        matrix_doc = frappe.get_doc("Approval Matrix", matrix.name)

        for level_row in matrix_doc.approval_levels:
            level: int = level_row.level
            based_on: str = level_row.based_on
            criteria: Optional[str] = level_row.criteria
            approver_role: str = level_row.approver_role
            fallback_role: Optional[str] = level_row.fallback_role

            if _matches_criteria(doc, based_on, criteria):
                users_with_role = get_users_with_role(approver_role)

                if users_with_role:
                    if level not in approvers:
                        approvers[level] = []
                    approvers[level] = users_with_role
                elif fallback_role:
                    fallback_users = get_users_with_role(fallback_role)
                    if level not in approvers:
                        approvers[level] = []
                    approvers[level] = fallback_users

    return approvers


# =============================================================================
# HELPER: approval matrix criteria matching
# =============================================================================
def _matches_criteria(doc: Document, based_on: str, criteria: Optional[str]) -> bool:
    if not criteria:
        return True

    if based_on == "Department":
        return doc.department == criteria
    elif based_on == "Request Type":
        return doc.request_type == criteria
    elif based_on == "Amount":
        try:
            amount = float(getattr(doc, "amount", 0) or 0)
            return amount >= float(criteria or 0)
        except (ValueError, TypeError):
            return False

    return False


# =============================================================================
# WHITELISTED API: Execution (creating target documents)
# =============================================================================
@frappe.whitelist()
def execute_request(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)

    if doc.status != "Approved":
        frappe.throw(_("Only approved requests can be executed"))

    if not doc.request_type:
        frappe.throw(_("Request Type is not set"))

    req_type = frappe.get_doc("Request Type", doc.request_type)

    if not getattr(req_type, "execution_mode", None):
        frappe.throw(_("Execution Mode not set for this Request Type"))

    mapping_names = frappe.get_all(
        "Document Mapping",
        filters={
            "request_type": doc.request_type,
            "execution_mode": req_type.execution_mode
        },
        pluck="name",
        order_by="modified desc",
        limit_page_length=1
    )

    if not mapping_names:
        frappe.throw(_("No Document Mapping found for this Request Type and Execution Mode"))

    mapping_doc = frappe.get_doc("Document Mapping", mapping_names[0])
    target_doctype = mapping_doc.get("target_doctype")

    if not target_doctype:
        doc.status = "In Progress"
        doc.save()
        return {
            'status': 'success',
            'message': 'Request is internal service - no document created',
            'created_doc': None
        }

    try:
        new_doc = create_target_document(doc, target_doctype, mapping_doc)

        doc.status = "In Progress"
        doc.execution_doctype = target_doctype
        doc.execution_docname = new_doc.name
        doc.save()

        return {
            'status': 'success',
            'message': f'{target_doctype} {new_doc.name} created successfully',
            'created_doc': new_doc.name
        }
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(f"Error executing request {request_name}: {str(e)}")
        frappe.throw(_("Error creating document: {0}").format(str(e)))

# =============================================================================
# HELPER: normalize requirements input (accepts list-of-rows or dict form)
# =============================================================================
def _normalize_requirements_input(requirements: Any = None, requirements_data: Any = None) -> Dict[str, Any]:
    if requirements_data:
        return dict(requirements_data)

    if requirements:
        result: Dict[str, Any] = {}
        for row in requirements:
            field_key = row.get("field_key") if isinstance(row, dict) else None
            if field_key:
                result[field_key] = row.get("value")
        return result

    return {}


# =============================================================================
# HELPER: build the mapped target document
# =============================================================================
def create_target_document(req_doc: Document, target_doctype: str, mapping_doc: Any) -> Document:
    new_doc = frappe.new_doc(target_doctype)
    req_meta = req_doc.meta
    target_meta = frappe.get_meta(target_doctype)

    mapping_details = mapping_doc.field_mapping or []

    for mapping in mapping_details:
        source_field = mapping.source_field
        target_field = mapping.target_field
        field_value = mapping.field_value

        if source_field and not req_meta.has_field(source_field):
            frappe.throw(_("Invalid source field '{0}' on {1} — check Document Mapping").format(
                source_field, req_doc.doctype))

        if target_field and not target_meta.has_field(target_field):
            frappe.throw(_("Invalid target field '{0}' on {1} — check Document Mapping").format(
                target_field, target_doctype))

        value = req_doc.get(source_field) if source_field else field_value

        if isinstance(value, str):
            value = strip_html(value)

        if target_field:
            new_doc.set(target_field, value)

    new_doc.insert(ignore_permissions=True)
    return new_doc


# =============================================================================
# WHITELISTED API: Status / retrieval
# =============================================================================
@frappe.whitelist()
def get_execution_status(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)

    return {
        'status': doc.status,
        'execution_doctype': getattr(doc, 'execution_doctype', None),
        'execution_docname': getattr(doc, 'execution_docname', None)
    }


@frappe.whitelist()
def get_request(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)
    return doc.as_dict()


# =============================================================================
# WHITELISTED API: Approve / Reject
# =============================================================================
@frappe.whitelist()
def approve_request(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)
    doc.reload()

    approvers = get_approvers(request_name)
    current_user = frappe.session.user

    is_approver = any(current_user in level for level in approvers.values())

    if not is_approver:
        frappe.throw(_("You are not authorized to approve this request"))

    if doc.status == "Pending Manager":
        doc.status = "Pending Department"
    elif doc.status == "Pending Department":
        doc.status = "Approved"
    else:
        frappe.throw(_("This request cannot be approved at this stage"))

    doc.save()
    frappe.msgprint(_("Request approved successfully"))

    return {
        'status': 'success',
        'message': f'Request {doc.name} approved',
        'new_status': doc.status
    }


@frappe.whitelist()
def reject_request(request_name: str, reason: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)
    doc.reload()

    approvers = get_approvers(request_name)
    current_user = frappe.session.user

    all_approvers = [user for level in approvers.values() for user in level]

    if current_user not in all_approvers and current_user != "Administrator":
        frappe.throw(_("You are not authorized to reject this request"))

    doc.reject_reason = reason
    doc.status = "Rejected"

    doc.save()
    frappe.msgprint(_("Request rejected successfully"))

    return {
        'status': 'success',
        'message': f'Request {doc.name} rejected',
        'reason': reason
    }


# =============================================================================
# WHITELISTED API: Create / Complete
# =============================================================================
@frappe.whitelist()
def create_request(
    request_type: str,
    naming_series: Optional[str] = None,
    requested_by: Optional[str] = None,
    request_date: Optional[str] = None,
    description: Optional[str] = None,
    requirements_data: Optional[dict] = None,
    requirements: Optional[list] = None,
    **kwargs
) -> Dict[str, Any]:

    try:
        new_doc = frappe.new_doc("Requests")

        new_doc.request_type = request_type
        new_doc.requested_by = requested_by or frappe.session.user
        new_doc.request_date = request_date or datetime.now()

        if description:
            new_doc.description = description

        for key, value in kwargs.items():
            if hasattr(new_doc, key):
                new_doc.set(key, value)

        values_by_key = _normalize_requirements_input(requirements, requirements_data)

        if values_by_key:
            rt_doc = frappe.get_doc("Request Type", request_type)
            valid_keys = {req.field_key for req in (rt_doc.requirements or [])}

            unknown_keys = [k for k in values_by_key if k not in valid_keys]
            if unknown_keys:
                frappe.throw(
                    _("Unknown requirement field(s) for request type '{0}': {1}").format(
                        request_type, ", ".join(unknown_keys)
                    ),
                    title=_("Invalid Field Key")
                )

            new_doc._pending_requirement_values = values_by_key

        new_doc.save()  
        frappe.msgprint(_("Request created successfully"))

        return {
            'status': 'success',
            'message': f'Request {new_doc.name} created successfully',
            'request_name': new_doc.name
        }

    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(f"Error creating request: {str(e)}")
        frappe.throw(_("Error creating request: {0}").format(str(e)))


@frappe.whitelist()
def update_request(
    request_name: str,
    requirements_data: Optional[dict] = None,
    requirements: Optional[list] = None,
    description: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)

    if doc.status != "Draft":
        frappe.throw(_("Only 'Draft' requests can be updated"))

    if description is not None:
        doc.description = description

    for key, value in kwargs.items():
        if hasattr(doc, key):
            doc.set(key, value)

    values_by_key = _normalize_requirements_input(requirements, requirements_data)

    if values_by_key:
        existing_rows = {row.field_key: row for row in (doc.requirements or []) if getattr(row, "field_key", None)}

        for field_key, value in values_by_key.items():
            if field_key in existing_rows:
                existing_rows[field_key].value = value
            else:
                frappe.throw(_("Unknown requirement field: {0}").format(field_key))

    try:

        doc.save()
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(f"Error updating request {request_name}: {str(e)}")
        frappe.throw(_("Error updating request: {0}").format(str(e)))

    frappe.msgprint(_("Request updated successfully"))

    return {
        'status': 'success',
        'message': f'Request {doc.name} updated',
        'request_name': doc.name
    }


@frappe.whitelist()
def complete_request(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)

    if doc.status != "In Progress":
        frappe.throw(_("Only 'In Progress' requests can be completed"))

    doc.status = "Completed"
    doc.save()
    frappe.msgprint(_("Request completed successfully"))

    return {
        'status': 'success',
        'message': f'Request {doc.name} completed',
        'new_status': doc.status
    }