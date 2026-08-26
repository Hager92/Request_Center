# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RequestApprovalTracking(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		approver: DF.Data
		approver_user: DF.Link | None
		employee: DF.Link | None
		level: DF.Int
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		step_status: DF.Literal["Pending", "Need Approval", "Approved", "Rejected"]
	# end: auto-generated types

	pass
