# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RequestMaterialItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from_warehouse: DF.Link | None
		fulfillment_path: DF.Literal["", "Inventory", "Internal Transfer", "Purchase", "Inventory and Internal Transfer", "Inventory and Purchase", "Internal Transfer and Purchase", "Inventory, Internal Transfer and Purchase"]
		item_code: DF.Link
		item_name: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		qty: DF.Float
		qty_to_issue: DF.Float
		qty_to_purchase: DF.Float
		qty_to_transfer: DF.Float
		stock_qty_available: DF.Float
		uom: DF.Link | None
		warehouse: DF.Link | None
	# end: auto-generated types

	pass
