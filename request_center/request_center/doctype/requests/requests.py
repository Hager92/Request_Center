from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from typing import List


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
    # Validate: sync requirements + check mandatory values
    # -------------------------------------------------------------------------
    def validate(self) -> None:
        self._sync_requirements_from_request_type()
        self._validate_mandatory_values()

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
            return False

        rt_doc = frappe.get_doc("Request Type", self.request_type)

        existing_values = {
            row.field_key: row.value
            for row in (self.requirements or [])
            if getattr(row, "field_key", None)
        }

        self.set("requirements", [])

        for src in (rt_doc.requirements or []):
            row = self.append("requirements", {})
            row.field_label = src.field_label
            row.field_key = src.field_key
            row.field_type = src.field_type
            row.field_options = getattr(src, "field_options", None)
            row.is_mandatory = src.mandatory
            row.sort_order = src.sort_order
            if src.field_key in existing_values:
                row.value = existing_values[src.field_key]

        return True

    # -------------------------------------------------------------------------
    # Mandatory validation: ensure required fields have values
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
                _("Please fill a value for mandatory field(s): {0}").format(", ".join(missing)),
                title=_("Missing Mandatory Value")
            )
            