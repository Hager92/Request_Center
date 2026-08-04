from __future__ import unicode_literals
import re
import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import getdate, get_datetime
from datetime import datetime
from typing import Optional, Dict, List, Any


# =============================================================================
# DOCTYPE CLASS: Requests
# =============================================================================
class Requests(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from request_center.request_center.doctype.request_requirement_value.request_requirement_value import RequestRequirementValue

        amended_from: DF.Link | None
        department: DF.Link
        department_manager: DF.Link | None
        description: DF.TextEditor | None
        execution_docname: DF.Data | None
        execution_doctype: DF.Data | None
        reject_reason: DF.Text | None
        request_date: DF.Datetime
        request_type: DF.Link
        requested_by: DF.Link
        requirements: DF.Table[RequestRequirementValue]
        status: DF.Literal["Draft", "Pending Manager", "Pending Department", "Approved", "In Progress", "Completed", "Rejected"]
    # end: auto-generated types

    # -------------------------------------------------------------------------
    # Validation entry point
    # -------------------------------------------------------------------------
    def validate(self) -> None:
        self._sync_requirements_from_request_type()
        self._validate_mandatory_values()

    # -------------------------------------------------------------------------
    # Requirements table sync (pulled from the linked Request Type)
    # -------------------------------------------------------------------------
    def _sync_requirements_from_request_type(self) -> bool:
        if not self.request_type:
            self.set("requirements", [])
            return False

        previous_rt = None if self.is_new() else self.get_db_value("request_type")
        request_type_changed = self.is_new() or previous_rt != self.request_type

        if not request_type_changed:
            return False

        rt_doc = frappe.get_doc("Request Type", self.request_type)

        # Preserve any values already entered before we rebuild the table
        existing_values = {
            row.field_key: row.value
            for row in (self.requirements or [])
            if getattr(row, "field_key", None)
        }

        self.set("requirements", [])

        for src in (rt_doc.requirements or []):
            row = self.append("requirements", {})
            row.field_label  = src.field_label
            row.field_key    = src.field_key
            row.field_type   = src.field_type
            row.field_options = getattr(src, "field_options", None)
            row.is_mandatory = src.mandatory
            row.sort_order   = src.sort_order
            if src.field_key in existing_values:
                row.value = existing_values[src.field_key]

        return True

    # -------------------------------------------------------------------------
    # Mandatory-field validation
    # -------------------------------------------------------------------------
    def _validate_mandatory_values(self) -> None:
        missing: List[str] = []

        for row in self.requirements:
            is_mandatory = getattr(row, "is_mandatory", 0)
            value = getattr(row, "value", None)

            if is_mandatory and not value:
                field_label = getattr(row, "field_label", "Unknown Field")
                missing.append(field_label)

        if missing:
            frappe.throw(
                _("Please fill a value for mandatory field(s): {0}")
                  .format(", ".join(missing)),
                title=_("Missing Mandatory Value")
            )


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


# -----------------------------------------------------------------------------
# Helper: approval matrix criteria matching
# -----------------------------------------------------------------------------
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
        except:
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

    if not req_type.execution_mode:
        frappe.throw(_("Execution Mode not set for this Request Type"))

    mapping = frappe.get_all(
        "Document Mapping",
        filters={
            "request_type": doc.request_type,
            "execution_mode": req_type.execution_mode
        },
        fields=["*"]
    )

    if not mapping:
        frappe.throw(_("No Document Mapping found for this Request Type and Execution Mode"))

    mapping_doc = mapping[0]
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
    except Exception as e:
        frappe.log_error(f"Error executing request {request_name}: {str(e)}")
        frappe.throw(_("Error creating document: {0}").format(str(e)))


# -----------------------------------------------------------------------------
# Helper: build the mapped target document
# -----------------------------------------------------------------------------
def create_target_document(req_doc, target_doctype, mapping_doc):

    new_doc = frappe.new_doc(target_doctype)

    mapping_details = mapping_doc.field_mapping or []

    for mapping in mapping_details:
        source_field = mapping.source_field
        target_field = mapping.target_field
        field_value = mapping.field_value

        if source_field:
            value = req_doc.get(source_field)
        else:
            value = field_value

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
def approve_request(request_name: str, comment: Optional[str] = None) -> Dict[str, Any]:

    doc = frappe.get_doc("Requests", request_name)
    doc.reload()

    approvers = get_approvers(request_name)
    current_user = frappe.session.user

    is_approver = False
    for level in approvers.values():
        if current_user in level:
            is_approver = True
            break

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
def reject_request(request_name: str, reason: Optional[str] = None) -> Dict[str, Any]:

    doc = frappe.get_doc("Requests", request_name)

    approvers = get_approvers(request_name)
    current_user = frappe.session.user

    is_approver = False
    for level in approvers.values():
        if current_user in level:
            is_approver = True
            break

    if not is_approver:
        frappe.throw(_("You are not authorized to reject this request"))

    doc.status = "Rejected"

    if reason:
        doc.reject_reason = reason

    doc.save()

    frappe.msgprint(_("Request rejected"))

    return {
        'status': 'success',
        'message': f'Request {doc.name} rejected',
        'reason': reason,
        'new_status': doc.status
    }


# =============================================================================
# WHITELISTED API: Create / Complete
# =============================================================================
@frappe.whitelist()
def create_request(
    request_type: str,
    department: str,
    naming_series: Optional[str] = None,
    requested_by: Optional[str] = None,
    request_date: Optional[str] = None,
    description: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:

    try:
        new_doc = frappe.new_doc("Requests")

        if naming_series:
            new_doc.naming_series = naming_series

        new_doc.request_type = request_type
        new_doc.department = department

        if requested_by:
            new_doc.requested_by = requested_by
        else:
            new_doc.requested_by = frappe.session.user

        if request_date:
            new_doc.request_date = request_date
        else:
            new_doc.request_date = datetime.now()

        if description:
            new_doc.description = description

        for key, value in kwargs.items():
            if hasattr(new_doc, key):
                new_doc.set(key, value)

        new_doc.save()
        frappe.msgprint(_("Request created successfully"))

        return {
            'status': 'success',
            'message': f'Request {new_doc.name} created successfully',
            'request_name': new_doc.name
        }
    except Exception as e:
        frappe.log_error(f"Error creating request: {str(e)}")
        frappe.throw(_("Error creating request: {0}").format(str(e)))


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