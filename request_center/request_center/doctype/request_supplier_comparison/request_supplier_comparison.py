# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RequestSupplierComparison(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		currency: DF.Link | None
		delivery_date: DF.Date | None
		delivery_days: DF.Int
		delivery_score: DF.Float
		delivery_time: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		price: DF.Currency
		price_score: DF.Float
		rank: DF.Int
		recommended: DF.Check
		selected: DF.Check
		supplier: DF.Link
		supplier_name: DF.Data | None
		supplier_quotation: DF.Link | None
		total_score: DF.Float
	# end: auto-generated types

	pass
