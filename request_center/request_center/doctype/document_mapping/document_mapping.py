# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DocumentMapping(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from request_center.request_center.doctype.mapping_detail.mapping_detail import MappingDetail

		execution_mode: DF.Link
		field_mapping: DF.Table[MappingDetail]
		request_type: DF.Link
		target_doctype: DF.Link | None
	# end: auto-generated types

	pass
