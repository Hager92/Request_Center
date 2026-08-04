# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RequestType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from request_center.request_center.doctype.request_type_requirement.request_type_requirement import RequestTypeRequirement

		department: DF.Link
		department_manager: DF.Link | None
		execution_mode: DF.Link | None
		is_active: DF.Check
		request_type_name: DF.Data
		requirements: DF.Table[RequestTypeRequirement]
	# end: auto-generated types

	pass
