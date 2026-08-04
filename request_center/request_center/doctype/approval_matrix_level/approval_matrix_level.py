# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ApprovalMatrixLevel(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		approver_role: DF.Link
		based_on: DF.Literal["Department", "Request Type", "Amount"]
		criteria: DF.Data | None
		fallback_role: DF.Link | None
		level: DF.Int
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
