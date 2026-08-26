# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from request_center.setup.request_categories import validate_request_category_name


class RequestCategory(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		category_name: DF.Data
		description: DF.SmallText | None
	# end: auto-generated types

	def validate(self):
		validate_request_category_name(self.category_name)

	def on_trash(self):
		frappe.throw(_("Predefined Request Categories cannot be deleted."))
