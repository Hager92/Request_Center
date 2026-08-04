# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class RequestTypeRequirement(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		field_key: DF.Data
		field_label: DF.Data
		field_type: DF.Literal["Data", "Date", "Datetime", "Check", "Currency", "Int", "Float", "Text"]
		mandatory: DF.Check
		options: DF.SmallText | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		sort_order: DF.Int
	# end: auto-generated types

	pass
