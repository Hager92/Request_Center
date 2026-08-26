from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from typing import List
from frappe.utils import flt, getdate, get_datetime, date_diff, nowdate, now_datetime


# =============================================================================
# DOCTYPE CLASS: Requests
# =============================================================================
class Requests(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from request_center.request_center.doctype.request_approval_tracking.request_approval_tracking import RequestApprovalTracking
        from request_center.request_center.doctype.request_linked_document.request_linked_document import RequestLinkedDocument
        from request_center.request_center.doctype.request_material_item.request_material_item import RequestMaterialItem
        from request_center.request_center.doctype.request_material_supplier.request_material_supplier import RequestMaterialSupplier
        from request_center.request_center.doctype.request_material_workflow_step.request_material_workflow_step import RequestMaterialWorkflowStep
        from request_center.request_center.doctype.request_requirement_value.request_requirement_value import RequestRequirementValue
        from request_center.request_center.doctype.request_supplier_comparison.request_supplier_comparison import RequestSupplierComparison

        amended_from: DF.Link | None
        approval_status_summary: DF.SmallText | None
        approval_tracking: DF.Table[RequestApprovalTracking]
        awarded_supplier: DF.Link | None
        category: DF.Data | None
        comparison_method: DF.Data | None
        comparison_notes: DF.SmallText | None
        current_approval_level: DF.Data | None
        current_approver: DF.SmallText | None
        current_approver_user: DF.Link | None
        days_elapsed: DF.Int
        department: DF.Link
        department_manager: DF.Link | None
        description: DF.TextEditor | None
        execution_docname: DF.Data | None
        execution_doctype: DF.Data | None
        expected_delivery_date: DF.Date | None
        fulfillment_path: DF.Data | None
        fulfillment_stage: DF.Data | None
        inventory_check_result: DF.Literal["", "Available", "Not Available", "Partially Available"]
        linked_documents: DF.Table[RequestLinkedDocument]
        material_items: DF.Table[RequestMaterialItem]
        material_suppliers: DF.Table[RequestMaterialSupplier]
        material_workflow: DF.Table[RequestMaterialWorkflowStep]
        purchase_order: DF.Link | None
        recommended_quotation: DF.Link | None
        reject_reason: DF.Text | None
        request_date: DF.Datetime
        request_type: DF.Link
        requested_by: DF.Link
        requirements: DF.Table[RequestRequirementValue]
        rfq: DF.Link | None
        selected_quotation: DF.Link | None
        status: DF.Literal["Draft", "Need Approval", "Approved", "Rejected", "Completed", "In Progress", "Pending Approval", "Pending Manager", "Pending Department"]
        supplier_comparison: DF.Table[RequestSupplierComparison]
        tender: DF.Link | None
        tender_notes: DF.SmallText | None
        tender_reference: DF.Data | None
    # end: auto-generated types

    # -------------------------------------------------------------------------
    # Validate: sync requirements + check mandatory values
    # -------------------------------------------------------------------------
    def validate(self) -> None:
        self._lock_identity_fields()
        self._sync_department_from_request_type()
        self._validate_status_change()
        self._validate_request_type_active()
        self._sync_requirements_from_request_type()
        self._validate_mandatory_values()
        self._validate_requirement_types()
        self._validate_approval_matrix()
        self._validate_material_items()
        self._update_list_tracking_fields()

    def before_insert(self) -> None:
        self.requested_by = _session_requested_by()
        if not self.request_date:
            self.request_date = now_datetime()
        self.status = "Draft"

    # -------------------------------------------------------------------------
    # Request Type sync: rebuild requirements table if changed
    # -------------------------------------------------------------------------
    def _sync_requirements_from_request_type(self) -> bool:
        if not self.request_type:
            self.set("requirements", [])
            return False

        previous_rt = None if self.is_new() else self.get_db_value("request_type")
        request_type_changed = self.is_new() or previous_rt != self.request_type

        if not request_type_changed:
            rt_doc = frappe.get_doc("Request Type", self.request_type)
            src_by_key = {
                src.field_key: src
                for src in (rt_doc.requirements or [])
                if getattr(src, "field_key", None)
            }
            for row in self.requirements or []:
                src = src_by_key.get(row.field_key)
                if not src:
                    continue
                row.field_label = src.field_label
                row.field_type = src.field_type
                row.options = getattr(src, "options", None)
                row.is_mandatory = src.mandatory
                row.sort_order = src.sort_order
            return False

        rt_doc = frappe.get_doc("Request Type", self.request_type)

        existing_values = {
            row.field_key: row.value
            for row in (self.requirements or [])
            if getattr(row, "field_key", None)
        }

        pending_values = getattr(self, "_pending_requirement_values", None) or {}
        existing_values.update(pending_values)

        self.set("requirements", [])

        for src in (rt_doc.requirements or []):
            row = self.append("requirements", {})
            row.field_label = src.field_label
            row.field_key = src.field_key
            row.field_type = src.field_type
            row.options = getattr(src, "options", None)
            row.is_mandatory = src.mandatory
            row.sort_order = src.sort_order
            if src.field_key in existing_values:
                row.value = existing_values[src.field_key]

        return True

    # -------------------------------------------------------------------------
    # Mandatory validation: ensure required fields have values
    # -------------------------------------------------------------------------
    def _validate_mandatory_values(self) -> None:
        if self.status in (None, "", "Draft"):
            return

        missing: List[str] = []

        for row in self.requirements:
            is_mandatory = getattr(row, "is_mandatory", 0)
            value = getattr(row, "value", None)

            if is_mandatory and not value:
                field_label = getattr(row, "field_label", "Unknown Field")
                missing.append(field_label)

        if missing:
            frappe.throw(
                _("Please fill a value for mandatory field(s): {0}").format(", ".join(missing)),
                title=_("Missing Mandatory Value")
            )

    # -------------------------------------------------------------------------
    # Requirement Type validation: ensure values match their types
    # -------------------------------------------------------------------------
    def _validate_requirement_types(self) -> None:
        errors: List[str] = []

        for row in self.requirements:
            value = getattr(row, "value", None)
            if value in (None, ""):
                continue

            field_type = getattr(row, "field_type", None)
            field_label = getattr(row, "field_label", None) or getattr(row, "field_key", "Unknown Field")

            try:
                if field_type == "Date":
                    getdate(value)
                elif field_type == "Datetime":
                    get_datetime(value)
                elif field_type == "Int":
                    int(str(value).strip())
                elif field_type in ("Float", "Currency", "Number"):
                    float(str(value).strip())
                elif field_type == "Check":
                    if str(value).strip().lower() not in ("0", "1", "true", "false"):
                        raise ValueError
                elif field_type == "Select":
                    opts = [
                        opt.strip()
                        for opt in str(getattr(row, "options", None) or "").split("\n")
                        if opt.strip()
                    ]
                    if opts and str(value).strip() not in opts:
                        raise ValueError
                elif field_type == "Link":
                    doctype = str(getattr(row, "options", None) or "").strip().split("\n")[0]
                    if doctype and not frappe.db.exists(doctype, value):
                        raise ValueError
            except (ValueError, TypeError):
                errors.append(_("'{0}' is not a valid {1} for field '{2}'").format(value, field_type, field_label))

        if errors:
            frappe.throw(
                "<br>".join(errors),
                title=_("Invalid Field Value")
            )

    def _lock_identity_fields(self) -> None:
        if self.is_new():
            self.requested_by = _session_requested_by()
            if not self.request_date:
                self.request_date = now_datetime()
            return
        previous = self.get_doc_before_save()
        if not previous:
            return
        self.requested_by = previous.requested_by
        self.request_date = previous.request_date or self.request_date or now_datetime()

    def _sync_department_from_request_type(self) -> None:
        if not self.request_type:
            return
        values = frappe.db.get_value(
            "Request Type",
            self.request_type,
            ["department", "department_manager", "category"],
            as_dict=True,
        )
        if not values:
            return
        self.department = values.department
        self.department_manager = values.department_manager
        self.category = values.category

    def _validate_status_change(self) -> None:
        if self.flags.get("request_center_workflow"):
            return
        if self.is_new():
            self.status = "Draft"
            return
        previous = self.get_doc_before_save()
        if not previous or previous.status == self.status:
            return
        if previous.status == "Draft" and self.status == "Need Approval":
            return
        frappe.throw(
            _("Status is read only. Use Submit, Approve, Reject, or the fulfillment actions.")
        )

    def _validate_request_type_active(self) -> None:
        if not self.request_type:
            return
        is_active = frappe.db.get_value("Request Type", self.request_type, "is_active")
        if is_active:
            return
        previous_type = None if self.is_new() else self.get_db_value("request_type")
        if not self.is_new() and previous_type == self.request_type:
            return
        frappe.throw(
            _("Request Type {0} is inactive and cannot be used for new requests").format(
                self.request_type
            )
        )

    def _validate_approval_matrix(self) -> None:
        if self.status in (None, "", "Draft", "Rejected"):
            return
        if not self.request_type:
            return
        from request_center.api.requests import has_approval_levels

        if not has_approval_levels(self.request_type):
            frappe.throw(
                _("Approval Levels are not set on Request Type {0}").format(self.request_type)
            )

    def _validate_material_items(self) -> None:
        category = self.category
        if not category and self.request_type:
            category = frappe.db.get_value("Request Type", self.request_type, "category")
        material_rows = [row for row in (self.material_items or []) if row.item_code]
        if material_rows and category != "Material Request":
            frappe.throw(_("Material items can only be used on a Material Request"))
        if category != "Material Request":
            return
        if self.status in (None, "", "Draft", "Rejected"):
            return
        rows = [row for row in (self.material_items or []) if row.item_code and flt(row.qty) > 0]
        if not rows:
            frappe.throw(_("Add at least one item with quantity for a Material Request"))
        for row in self.material_items or []:
            if not row.item_code:
                continue
            if flt(row.qty) <= 0:
                frappe.throw(_("Quantity must be greater than zero for item {0}").format(row.item_code))

    def _update_list_tracking_fields(self) -> None:
        if self.request_type:
            self.category = frappe.db.get_value("Request Type", self.request_type, "category")
        else:
            self.category = None

        if self.request_date:
            self.days_elapsed = date_diff(nowdate(), getdate(self.request_date))
        else:
            self.days_elapsed = 0

        from request_center.api.requests import apply_approval_progress_to_doc

        apply_approval_progress_to_doc(self)

    def on_update(self) -> None:
        from request_center.notifications import notify_request_change

        notify_request_change(self, previous=self.get_doc_before_save())


def _session_requested_by() -> str:
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("You must be logged in to create a request"))
    if user == "Administrator":
        return user
    if not frappe.db.exists("Employee", {"user_id": user}):
        frappe.throw(
            _("Requested By is taken from the current employee. Link an Employee record to your user.")
        )
    return user


def update_request_list_tracking() -> None:
    today = nowdate()
    rows = frappe.get_all(
        "Requests",
        fields=["name", "request_date", "status", "request_type"],
    )
    from request_center.api.requests import apply_approval_progress_to_doc

    for row in rows:
        try:
            days = date_diff(today, getdate(row.request_date)) if row.request_date else 0
            values = {"days_elapsed": days}
            doc = frappe.get_doc("Requests", row.name)
            apply_approval_progress_to_doc(doc)
            values["current_approval_level"] = doc.current_approval_level
            values["current_approver"] = doc.current_approver
            values["current_approver_user"] = getattr(doc, "current_approver_user", None)
            values["approval_status_summary"] = getattr(doc, "approval_status_summary", None)
            frappe.db.set_value("Requests", row.name, values, update_modified=False)
        except Exception:
            frappe.log_error(title=f"Request list tracking update failed for {row.name}")
