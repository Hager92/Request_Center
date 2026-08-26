# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TenderItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		item_code: DF.Link
		item_name: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		qty: DF.Float
		uom: DF.Link | None
		warehouse: DF.Link | None
	# end: auto-generated types

	pass
