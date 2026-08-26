from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from typing import Optional, Dict, List, Any, Tuple
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
# Approval workflow (configuration-driven from Request Type Approval Levels)
# Architecture: Submit → Approval Levels → Approved → Service / Other Process
#               or Material Request (Inventory Check → Transfer or Purchase → Completed)
# =============================================================================
PENDING_APPROVAL_STATUSES = (
    "Need Approval",
    "Pending Approval",
    "Pending Manager",
    "Pending Department",
)
CLOSED_APPROVAL_STATUSES = ("Approved", "In Progress", "Completed")
NEED_APPROVAL_STATUS = "Need Approval"


def _get_approval_level_rows(request_type: Optional[str]) -> List[Any]:
    if not request_type:
        return []
    req_type = frappe.get_doc("Request Type", request_type)
    levels = list(req_type.get("approval_levels") or [])
    return sorted(levels, key=lambda row: int(getattr(row, "level", 0) or 0))


def has_approval_levels(request_type: Optional[str]) -> bool:
    return bool(_get_approval_level_rows(request_type))


def _require_approval_levels(request_type: str) -> None:
    if not has_approval_levels(request_type):
        frappe.throw(
            _("Approval Levels are not set on Request Type {0}").format(request_type)
        )


def _approvers_from_levels(doc, level_rows, required_only: bool = True) -> Dict[int, List[str]]:
    approvers: Dict[int, List[str]] = {}

    for level_row in level_rows:
        if required_only and not _row_is_required(level_row):
            continue

        level: int = level_row.level
        user = _user_for_level_row(doc, level_row)
        if user:
            approvers[level] = [user]
            continue

        based_on: str = getattr(level_row, "based_on", None)
        criteria: Optional[str] = getattr(level_row, "criteria", None)
        approver_role: str = getattr(level_row, "approver_role", None)
        fallback_role: Optional[str] = getattr(level_row, "fallback_role", None)
        if not approver_role:
            continue
        if based_on and not _matches_criteria(doc, based_on, criteria):
            continue

        users_with_role = _users_for_approver_role(doc, approver_role)
        if users_with_role:
            approvers[level] = users_with_role
        elif fallback_role:
            fallback_users = _users_for_approver_role(doc, fallback_role)
            if fallback_users:
                approvers[level] = fallback_users

    return approvers


def _row_is_required(level_row) -> bool:
    if not hasattr(level_row, "required"):
        return True
    required = getattr(level_row, "required", None)
    if required is None:
        return True
    return bool(required)


def _user_for_level_row(doc, level_row) -> Optional[str]:
    employee = getattr(level_row, "approver", None)
    if not employee:
        return None
    if not frappe.db.exists("Employee", employee):
        return None
    return frappe.db.get_value("Employee", employee, "user_id")


def _users_for_approver_role(doc, role_name: Optional[str]) -> List[str]:
    if not role_name:
        return []
    if role_name == "Department Manager":
        manager = getattr(doc, "department_manager", None)
        if not manager and getattr(doc, "request_type", None):
            manager = frappe.db.get_value(
                "Request Type", doc.request_type, "department_manager"
            )
        if manager:
            return [manager]
    return get_users_with_role(role_name)


def _sorted_levels(approvers: Dict[Any, List[str]]) -> List[int]:
    return sorted(int(level) for level in approvers.keys())


def _stored_approval_level(doc) -> Optional[int]:
    stored = getattr(doc, "current_approval_level", None)
    try:
        return int(stored) if stored not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _users_for_current_status(doc, approvers: Dict[Any, List[str]]) -> List[str]:
    level = _waiting_level(doc, approvers)
    if level is None:
        return []
    return approvers.get(level) or approvers.get(str(level)) or []


def _waiting_level(doc, approvers: Dict[Any, List[str]]) -> Optional[int]:
    levels = _sorted_levels(approvers)
    if not levels:
        return None

    stored_level = _stored_approval_level(doc)
    if stored_level is None:
        return levels[0]

    remaining = [level for level in levels if level >= stored_level]
    if remaining:
        return remaining[0]
    return None


def _required_approvers(doc) -> Dict[int, List[str]]:
    return _approvers_from_levels(
        doc, _get_approval_level_rows(getattr(doc, "request_type", None)), required_only=True
    )


def _is_current_approver(doc, approvers: Optional[Dict[Any, List[str]]] = None) -> bool:
    user = frappe.session.user
    if user == "Administrator":
        return True
    approvers = approvers if approvers is not None else _required_approvers(doc)
    return user in _users_for_current_status(doc, approvers)


def get_current_approval_state(doc) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    status = getattr(doc, "status", None)
    if status in CLOSED_APPROVAL_STATUSES:
        return None, None, None
    if not getattr(doc, "request_type", None):
        return None, None, None

    level_rows = _get_approval_level_rows(doc.request_type)
    if not level_rows:
        return None, None, None

    approvers = _approvers_from_levels(doc, level_rows, required_only=True)
    if not _sorted_levels(approvers):
        return None, None, None

    level = _waiting_level(doc, approvers)
    users = _users_for_current_status(doc, approvers)
    if level is None:
        return None, None, None

    from frappe.utils import get_fullname

    names = [get_fullname(user) or user for user in users] if users else []
    return str(level), ", ".join(names) or None, (users[0] if users else None)


def get_current_approval_display(doc) -> Tuple[Optional[str], Optional[str]]:
    level, approver, _user = get_current_approval_state(doc)
    return level, approver


def _employee_display_name(employee: Optional[str], user: Optional[str] = None) -> str:
    from frappe.utils import get_fullname

    if employee and frappe.db.exists("Employee", employee):
        return frappe.db.get_value("Employee", employee, "employee_name") or employee
    if user:
        return get_fullname(user) or user
    return employee or user or ""


def _step_status_for(parent_status: Optional[str], level: int, waiting_level: Optional[int]) -> str:
    if parent_status in CLOSED_APPROVAL_STATUSES:
        return "Approved"
    if parent_status == "Draft" or waiting_level is None:
        return "Pending"
    if parent_status == "Rejected":
        if level < waiting_level:
            return "Approved"
        if level == waiting_level:
            return "Rejected"
        return "Pending"
    if parent_status in PENDING_APPROVAL_STATUSES:
        if level < waiting_level:
            return "Approved"
        if level == waiting_level:
            return NEED_APPROVAL_STATUS
        return "Pending"
    return "Pending"


def _approval_status_summary(status: Optional[str], level: Optional[str], approver: Optional[str]) -> str:
    if status == "Draft":
        return _("Draft")
    if status in PENDING_APPROVAL_STATUSES:
        if level and approver:
            return _("Need Approval — Level {0}: {1}").format(level, approver)
        return _("Need Approval")
    if status == "Rejected":
        if level and approver:
            return _("Rejected — Level {0}: {1}").format(level, approver)
        return _("Rejected")
    if status == "Approved":
        return _("Approved")
    if status == "In Progress":
        return _("In Progress")
    if status == "Completed":
        return _("Completed")
    return status or ""


def sync_approval_tracking(doc) -> None:
    if not hasattr(doc, "approval_tracking"):
        return

    level, approver, user = get_current_approval_state(doc)
    waiting_level = int(level) if level not in (None, "") else None
    status = getattr(doc, "status", None)

    if not getattr(doc, "request_type", None):
        doc.set("approval_tracking", [])
        if hasattr(doc, "approval_status_summary"):
            doc.approval_status_summary = _approval_status_summary(status, None, None)
        return

    level_rows = [
        row
        for row in _get_approval_level_rows(doc.request_type)
        if _row_is_required(row)
    ]
    existing = {
        int(row.level): row
        for row in (doc.approval_tracking or [])
        if getattr(row, "level", None) not in (None, "")
    }
    rebuild = (not existing) or (status == "Draft") or (set(existing.keys()) != {int(r.level) for r in level_rows})

    if rebuild:
        doc.set("approval_tracking", [])
        for level_row in level_rows:
            employee = getattr(level_row, "approver", None)
            row_user = _user_for_level_row(doc, level_row)
            doc.append(
                "approval_tracking",
                {
                    "level": level_row.level,
                    "employee": employee,
                    "approver_user": row_user,
                    "approver": _employee_display_name(employee, row_user),
                    "step_status": "Pending",
                },
            )

    for row in doc.approval_tracking or []:
        row.step_status = _step_status_for(status, int(row.level), waiting_level)

    if hasattr(doc, "approval_status_summary"):
        summary_approver = approver
        if not summary_approver and waiting_level is not None:
            for row in doc.approval_tracking or []:
                if int(row.level) == waiting_level:
                    summary_approver = row.approver
                    break
        doc.approval_status_summary = _approval_status_summary(status, level, summary_approver)


def apply_approval_progress_to_doc(doc) -> None:
    level, approver, user = get_current_approval_state(doc)
    doc.current_approval_level = level
    doc.current_approver = approver
    if hasattr(doc, "current_approver_user"):
        doc.current_approver_user = user
    sync_approval_tracking(doc)
    stage = getattr(doc, "fulfillment_stage", None)
    result = getattr(doc, "inventory_check_result", None)
    if getattr(doc, "status", None) == "In Progress" and stage:
        if result:
            doc.approval_status_summary = _("In Progress — {0} ({1})").format(stage, result)
        else:
            doc.approval_status_summary = _("In Progress — {0}").format(stage)


def _persist_approval_fields(doc) -> None:
    old_status = frappe.db.get_value("Requests", doc.name, "status")
    old_level = frappe.db.get_value("Requests", doc.name, "current_approval_level")
    values = {
        "status": doc.status,
        "current_approval_level": doc.current_approval_level,
        "current_approver": doc.current_approver,
        "reject_reason": doc.reject_reason,
        "approval_status_summary": getattr(doc, "approval_status_summary", None),
    }
    if hasattr(doc, "current_approver_user"):
        values["current_approver_user"] = doc.current_approver_user
    frappe.db.set_value("Requests", doc.name, values, update_modified=True)
    doc.reload()
    from request_center.notifications import notify_request_change

    notify_request_change(doc, old_status=old_status, old_level=old_level)


def _save_request(doc) -> None:
    from frappe.model.workflow import WorkflowPermissionError, WorkflowTransitionError

    apply_approval_progress_to_doc(doc)
    doc.flags.ignore_permissions = True
    doc.flags.request_center_workflow = True
    try:
        doc.save()
    except (WorkflowPermissionError, WorkflowTransitionError):
        _persist_approval_fields(doc)


@frappe.whitelist()
def get_approver_preview(
    request_type: str,
    department: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    if not request_type:
        return {"current_approval_level": None, "current_approver": None}

    doc = frappe.new_doc("Requests")
    doc.request_type = request_type
    if department:
        doc.department = department
    doc.status = status or "Draft"
    level, approver = get_current_approval_display(doc)
    return {
        "current_approval_level": level,
        "current_approver": approver,
        "approval_status_summary": _approval_status_summary(doc.status, level, approver),
    }


@frappe.whitelist()
def get_approval_tracking_preview(
    request_type: str,
    department: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    if not request_type:
        return {"rows": [], "approval_status_summary": None}
    doc = frappe.new_doc("Requests")
    doc.request_type = request_type
    if department:
        doc.department = department
    doc.status = status or "Draft"
    apply_approval_progress_to_doc(doc)
    return {
        "approval_status_summary": getattr(doc, "approval_status_summary", None),
        "current_approval_level": doc.current_approval_level,
        "current_approver": doc.current_approver,
        "rows": [
            {
                "level": row.level,
                "approver": row.approver,
                "step_status": row.step_status,
            }
            for row in (doc.approval_tracking or [])
        ],
    }


@frappe.whitelist()
def get_approvers_preview(
    request_type: str,
    department: Optional[str] = None,
) -> Dict[int, List[str]]:
    if not request_type:
        return {}
    level_rows = _get_approval_level_rows(request_type)
    if not level_rows:
        return {}
    doc = frappe.new_doc("Requests")
    doc.request_type = request_type
    if department:
        doc.department = department
    return _approvers_from_levels(doc, level_rows, required_only=False)


@frappe.whitelist()
def get_approvers(request_name: str) -> Dict[int, List[str]]:
    doc = frappe.get_doc("Requests", request_name)

    if not doc.request_type:
        return {}

    _require_approval_levels(doc.request_type)
    return _approvers_from_levels(
        doc, _get_approval_level_rows(doc.request_type), required_only=False
    )


def _unique_request_rows(rows: List[Any]) -> List[Any]:
    seen: set[str] = set()
    unique: List[Any] = []
    for row in rows:
        if row.name in seen:
            continue
        seen.add(row.name)
        unique.append(row)
    return unique


def _collect_to_review(request_type: Optional[str] = None) -> List[Any]:
    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    type_filter: Dict[str, Any] = {}
    if request_type:
        type_filter["request_type"] = request_type

    rows: List[Any] = []

    def add(extra: Dict[str, Any]) -> None:
        filters = {**type_filter, **extra}
        rows.extend(
            frappe.get_all(
                "Requests",
                filters=filters,
                fields=["name", "request_type", "status"],
            )
        )

    pending = frappe.get_all(
        "Requests",
        filters={**type_filter, "status": ["in", list(PENDING_APPROVAL_STATUSES)]},
        fields=["name", "request_type", "status"],
    )
    levels_by_type: Dict[str, List[Any]] = {}
    for row in pending:
        request_type_name = row.request_type
        if request_type_name not in levels_by_type:
            levels_by_type[request_type_name] = _get_approval_level_rows(request_type_name)
        level_rows = levels_by_type[request_type_name]
        if not level_rows:
            continue
        doc = frappe.get_doc("Requests", row.name)
        approvers = _approvers_from_levels(doc, level_rows)
        if user in _users_for_current_status(doc, approvers):
            rows.append(row)

    if "Execution Team" in roles:
        add({"status": ["in", ["Approved", "In Progress"]]})

    return _unique_request_rows(rows)


@frappe.whitelist()
def get_to_review_inbox() -> Dict[str, Any]:
    rows = _collect_to_review()
    counts: Dict[str, int] = {}
    names_by_type: Dict[str, List[str]] = {}

    for row in rows:
        request_type = row.request_type
        if not request_type:
            continue
        counts[request_type] = counts.get(request_type, 0) + 1
        names_by_type.setdefault(request_type, []).append(row.name)

    return {
        "counts": counts,
        "names_by_type": names_by_type,
    }


@frappe.whitelist()
def get_portal_data() -> Dict[str, Any]:
    types = frappe.get_all(
        "Request Type",
        filters={"is_active": 1},
        fields=["name", "department", "category", "icon"],
        order_by="name asc",
        limit_page_length=200,
    )
    inbox_rows = _collect_to_review()
    counts: Dict[str, int] = {}
    names_by_type: Dict[str, List[str]] = {}
    for row in inbox_rows:
        if not row.request_type:
            continue
        counts[row.request_type] = counts.get(row.request_type, 0) + 1
        names_by_type.setdefault(row.request_type, []).append(row.name)

    review_names = [row.name for row in inbox_rows]
    to_review: List[Dict[str, Any]] = []
    if review_names:
        to_review = frappe.get_all(
            "Requests",
            filters={"name": ["in", review_names]},
            fields=[
                "name",
                "request_type",
                "status",
                "requested_by",
                "current_approval_level",
                "current_approver",
                "approval_status_summary",
                "modified",
            ],
            order_by="modified desc",
        )

    my_requests = frappe.get_all(
        "Requests",
        or_filters=[
            ["requested_by", "=", frappe.session.user],
            ["owner", "=", frappe.session.user],
        ],
        fields=[
            "name",
            "request_type",
            "status",
            "category",
            "current_approval_level",
            "current_approver",
            "approval_status_summary",
            "fulfillment_stage",
            "inventory_check_result",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=25,
    )

    return {
        "types": types,
        "counts": counts,
        "names_by_type": names_by_type,
        "to_review": to_review,
        "my_requests": my_requests,
    }


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
            amount = 0

            for row in getattr(doc, "requirements", []):  
                if row.field_key == "amount":
                    amount = float(row.value or 0)
                    break  

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

    from request_center.material_fulfillment import is_material_request, start_material_fulfillment

    if is_material_request(doc):
        result = start_material_fulfillment(request_name)
        return {
            "status": result.get("status"),
            "message": result.get("message"),
            "created_doc": ", ".join(result.get("created_docs") or []),
            "fulfillment_path": result.get("fulfillment_path"),
            "fulfillment_stage": result.get("fulfillment_stage"),
            "inventory_check_result": result.get("inventory_check_result"),
        }

    req_type = frappe.get_doc("Request Type", doc.request_type)
    execution_mode = _resolve_execution_mode(req_type)
    mode_doc = frappe.get_doc("Execution Mode", execution_mode) if execution_mode else None
    mapping_doc = _document_mapping_for(doc.request_type, execution_mode)
    target_doctype = _target_doctype_for_mode(mode_doc, mapping_doc)

    if target_doctype:
        try:
            new_doc = create_target_document(doc, target_doctype, mapping_doc)
        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.log_error(f"Error executing request {request_name}: {str(e)}")
            frappe.throw(_("Error creating document: {0}").format(str(e)))

        return _mark_service_in_progress(
            doc,
            message=_("{0} {1} created using Execution Mode {2}").format(
                target_doctype, new_doc.name, execution_mode
            ),
            created_doc=new_doc.name,
            target_doctype=target_doctype,
        )

    return _mark_service_in_progress(
        doc,
        message=_("Service / Other Process started with Execution Mode {0}.").format(
            execution_mode or _("Internal Service")
        ),
        created_doc=None,
        target_doctype=None,
    )


def _resolve_execution_mode(req_type) -> Optional[str]:
    mode = getattr(req_type, "execution_mode", None)
    if mode and frappe.db.exists("Execution Mode", mode):
        return mode

    mapped = frappe.get_all(
        "Document Mapping",
        filters={"request_type": req_type.name},
        pluck="execution_mode",
        order_by="modified desc",
        limit_page_length=1,
    )
    if mapped and mapped[0] and frappe.db.exists("Execution Mode", mapped[0]):
        return mapped[0]

    for preferred in ("Internal Service", "HR", "IT", "External"):
        if frappe.db.exists("Execution Mode", preferred):
            return preferred

    any_mode = frappe.get_all("Execution Mode", pluck="name", limit_page_length=1)
    return any_mode[0] if any_mode else None


def _document_mapping_for(request_type: str, execution_mode: Optional[str]):
    filters: Dict[str, Any] = {"request_type": request_type}
    if execution_mode:
        filters["execution_mode"] = execution_mode
    names = frappe.get_all(
        "Document Mapping",
        filters=filters,
        pluck="name",
        order_by="modified desc",
        limit_page_length=1,
    )
    if not names and execution_mode:
        names = frappe.get_all(
            "Document Mapping",
            filters={"request_type": request_type},
            pluck="name",
            order_by="modified desc",
            limit_page_length=1,
        )
    if not names:
        return None
    return frappe.get_doc("Document Mapping", names[0])


def _target_doctype_for_mode(mode_doc, mapping_doc) -> Optional[str]:
    candidates = []
    if mapping_doc:
        candidates.append(getattr(mapping_doc, "target_doctype", None))
    if mode_doc:
        candidates.append(getattr(mode_doc, "erp_output", None))
    for name in candidates:
        if name and frappe.db.exists("DocType", name):
            return name
    return None


def _mark_service_in_progress(
    doc,
    message: str,
    created_doc: Optional[str],
    target_doctype: Optional[str],
) -> Dict[str, Any]:
    doc.status = "In Progress"
    doc.fulfillment_path = "Service / Other Process"
    doc.fulfillment_stage = "Service / Other Process"
    if target_doctype:
        doc.execution_doctype = target_doctype
    if created_doc:
        doc.execution_docname = created_doc
    doc.flags.request_center_workflow = True
    doc.save()
    return {
        "status": "success",
        "message": message,
        "created_doc": created_doc,
    }


def try_start_service_process(request_name: str) -> Dict[str, Any]:
    try:
        return execute_request(request_name)
    except frappe.ValidationError as e:
        frappe.log_error(title=f"Service / Other Process could not start for {request_name}")
        return {
            "status": "pending",
            "message": _("Approved. Service / Other Process is next: {0}").format(str(e)),
        }
    except Exception:
        frappe.log_error(title=f"Service / Other Process could not start for {request_name}")
        return {
            "status": "pending",
            "message": _("Approved. Start the Service / Other Process from the request."),
        }


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

    mapping_details = (mapping_doc.field_mapping or []) if mapping_doc else []

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
def get_approval_action(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)
    if doc.status not in PENDING_APPROVAL_STATUSES:
        return {"can_act": False, "is_final": False, "level": None}

    if not doc.request_type:
        return {"can_act": False, "is_final": False, "level": None}

    _require_approval_levels(doc.request_type)
    approvers = _required_approvers(doc)
    levels = _sorted_levels(approvers)
    current_level = _waiting_level(doc, approvers)
    is_final = bool(levels) and current_level == levels[-1]
    return {
        "can_act": _is_current_approver(doc, approvers),
        "is_final": is_final,
        "level": str(current_level) if current_level is not None else None,
    }


@frappe.whitelist()
def apply_workflow(doc: Any, action: str) -> Any:
    from frappe.model.workflow import apply_workflow as frappe_apply_workflow

    parsed = frappe.parse_json(doc) if isinstance(doc, str) else doc
    if isinstance(parsed, dict):
        doctype = parsed.get("doctype")
        name = parsed.get("name")
    else:
        doctype = getattr(parsed, "doctype", None)
        name = getattr(parsed, "name", None)

    if doctype == "Requests" and action == "Approve":
        approve_request(name)
        return frappe.get_doc("Requests", name)
    if doctype == "Requests" and action == "Reject":
        reject_request(name, reason=None)
        return frappe.get_doc("Requests", name)
    if doctype == "Requests" and action == "Assign":
        from request_center.material_fulfillment import is_material_request

        request_doc = frappe.get_doc("Requests", name)
        if is_material_request(request_doc):
            from request_center.material_workflow import run_inventory_check

            run_inventory_check(name)
        else:
            execute_request(name)
        return frappe.get_doc("Requests", name)
    if doctype == "Requests" and action == "Complete":
        complete_request(name)
        return frappe.get_doc("Requests", name)

    return frappe_apply_workflow(doc, action)


@frappe.whitelist()
def approve_request(request_name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)
    doc.reload()

    if doc.status not in PENDING_APPROVAL_STATUSES:
        frappe.throw(_("This request cannot be approved at this stage"))

    if not doc.request_type:
        frappe.throw(_("Request Type is not set"))

    _require_approval_levels(doc.request_type)
    approvers = _required_approvers(doc)
    if not approvers:
        frappe.throw(_("No approvers match this request on the Request Type Approval Levels"))

    if not _is_current_approver(doc, approvers):
        frappe.throw(_("You are not authorized to approve this request"))

    levels = _sorted_levels(approvers)
    current_level = _waiting_level(doc, approvers)
    if current_level is None:
        frappe.throw(_("This request cannot be approved at this stage"))

    current_index = levels.index(current_level)
    if current_index >= len(levels) - 1:
        doc.status = "Approved"
        doc.current_approval_level = None
        message = _("Request approved successfully")
    else:
        next_level = levels[current_index + 1]
        doc.current_approval_level = str(next_level)
        doc.status = NEED_APPROVAL_STATUS
        message = _("Level {0} approved. Waiting on Level {1}.").format(current_level, next_level)

    _save_request(doc)

    if current_index >= len(levels) - 1:
        from request_center.material_fulfillment import is_material_request, try_start_material_fulfillment

        if is_material_request(doc):
            result = try_start_material_fulfillment(doc.name)
        else:
            result = try_start_service_process(doc.name)
        if result:
            doc.reload()
            extra = result.get("message")
            if extra:
                message = f"{message}. {extra}"

    frappe.msgprint(message)

    return {
        "status": "success",
        "message": message,
        "new_status": doc.status,
        "current_approval_level": doc.current_approval_level,
        "current_approver": doc.current_approver,
        "fulfillment_path": getattr(doc, "fulfillment_path", None),
    }


@frappe.whitelist()
def reject_request(request_name: str, reason: Optional[str] = None) -> Dict[str, Any]:
    doc = frappe.get_doc("Requests", request_name)
    doc.reload()

    if doc.status not in PENDING_APPROVAL_STATUSES:
        frappe.throw(_("This request cannot be rejected at this stage"))

    if not doc.request_type:
        frappe.throw(_("Request Type is not set"))

    _require_approval_levels(doc.request_type)
    approvers = _required_approvers(doc)
    if not approvers:
        frappe.throw(_("No approvers match this request on the Request Type Approval Levels"))

    if not _is_current_approver(doc, approvers):
        frappe.throw(_("You are not authorized to reject this request"))

    doc.reject_reason = reason or _("Rejected")
    doc.status = "Rejected"

    _save_request(doc)
    frappe.msgprint(_("Request rejected successfully"))

    return {
        "status": "success",
        "message": _("Request {0} rejected").format(doc.name),
        "reason": doc.reject_reason,
        "new_status": doc.status,
    }


PROTECTED_REQUEST_FIELDS = frozenset(
    {
        "status",
        "current_approval_level",
        "current_approver",
        "current_approver_user",
        "approval_status_summary",
        "approval_tracking",
        "requested_by",
        "request_date",
        "department",
        "department_manager",
        "category",
        "name",
        "owner",
        "amended_from",
        "naming_series",
    }
)


def _apply_writable_kwargs(doc, kwargs: Optional[dict]) -> None:
    for key, value in (kwargs or {}).items():
        if key in PROTECTED_REQUEST_FIELDS or key in ("material_items", "requirements", "requirements_data"):
            continue
        if hasattr(doc, key):
            doc.set(key, value)


@frappe.whitelist()
def create_request(
    request_type: str,
    naming_series: Optional[str] = None,
    requested_by: Optional[str] = None,
    request_date: Optional[str] = None,
    description: Optional[str] = None,
    requirements_data: Optional[dict] = None,
    requirements: Optional[list] = None,
    material_items: Optional[list] = None,
    **kwargs
) -> Dict[str, Any]:

    try:
        new_doc = frappe.new_doc("Requests")

        new_doc.request_type = request_type
        new_doc.status = "Draft"

        if description:
            new_doc.description = description

        if material_items:
            parsed_items = frappe.parse_json(material_items) if isinstance(material_items, str) else material_items
            for row in parsed_items or []:
                new_doc.append("material_items", row)

        _apply_writable_kwargs(new_doc, kwargs)

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

    _apply_writable_kwargs(doc, kwargs)

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

    from request_center.material_fulfillment import is_material_request
    from request_center.material_workflow import material_workflow_complete

    if is_material_request(doc) and not material_workflow_complete(doc):
        frappe.throw(_("Finish the Material Request workflow before completing this request"))

    doc.status = "Completed"
    doc.fulfillment_stage = "Completed"
    doc.flags.request_center_workflow = True
    doc.save()
    frappe.msgprint(_("Request completed successfully"))

    return {
        'status': 'success',
        'message': f'Request {doc.name} completed',
        'new_status': doc.status
    }