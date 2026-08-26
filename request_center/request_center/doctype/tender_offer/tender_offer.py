# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TenderOffer(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		expected_delivery_date: DF.Date | None
		grand_total: DF.Currency
		offer_status: DF.Literal["Received", "Submitted", "Awarded", "Rejected"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		supplier: DF.Link
		supplier_quotation: DF.Link | None
	# end: auto-generated types

	pass
