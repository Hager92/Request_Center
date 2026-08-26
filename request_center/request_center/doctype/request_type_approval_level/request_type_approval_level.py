# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RequestTypeApprovalLevel(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		approver: DF.Link
		level: DF.Int
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		required: DF.Check
	# end: auto-generated types

	pass
