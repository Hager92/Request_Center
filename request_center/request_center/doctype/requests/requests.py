from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _
from typing import List
from frappe.utils import getdate, get_datetime


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
        self._validate_requirement_types()

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
                elif field_type in ("Float", "Currency"):
                    float(str(value).strip())
                elif field_type == "Check":
                    if str(value).strip().lower() not in ("0", "1", "true", "false"):
                        raise ValueError
            except (ValueError, TypeError):
                errors.append(_("'{0}' is not a valid {1} for field '{2}'").format(value, field_type, field_label))

        if errors:
            frappe.throw(
                "<br>".join(errors),
                title=_("Invalid Field Value")
            )