# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ApprovalMatrix(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from request_center.request_center.doctype.approval_matrix_level.approval_matrix_level import ApprovalMatrixLevel

		approval_levels: DF.Table[ApprovalMatrixLevel]
		approval_type_name: DF.Data
		description: DF.Text | None
		is_active: DF.Check
	# end: auto-generated types

	pass
