# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class Tender(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from request_center.request_center.doctype.tender_item.tender_item import TenderItem
		from request_center.request_center.doctype.tender_offer.tender_offer import TenderOffer
		from request_center.request_center.doctype.tender_purchase_order.tender_purchase_order import TenderPurchaseOrder
		from request_center.request_center.doctype.tender_rfq.tender_rfq import TenderRFQ
		from request_center.request_center.doctype.tender_supplier.tender_supplier import TenderSupplier

		awarded_quotation: DF.Link | None
		awarded_supplier: DF.Link | None
		closing_date: DF.Date | None
		company: DF.Link | None
		external_reference: DF.Data | None
		items: DF.Table[TenderItem]
		material_request: DF.Link | None
		notes: DF.TextEditor | None
		offers: DF.Table[TenderOffer]
		opening_date: DF.Date | None
		purchase_orders: DF.Table[TenderPurchaseOrder]
		request: DF.Link
		rfqs: DF.Table[TenderRFQ]
		status: DF.Literal["Draft", "Open", "Offers Received", "Awarded", "Closed"]
		suppliers: DF.Table[TenderSupplier]
		title: DF.Data
	# end: auto-generated types

	def validate(self) -> None:
		if not self.items:
			frappe.throw(_("Add at least one requested product to the Tender"))
		seen_items = set()
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Quantity must be greater than zero for item {0}").format(row.item_code))
			if row.item_code in seen_items:
				continue
			seen_items.add(row.item_code)
		seen_suppliers = set()
		for row in self.suppliers:
			if not row.supplier:
				continue
			if row.supplier in seen_suppliers:
				frappe.throw(_("Supplier {0} is selected more than once").format(row.supplier))
			seen_suppliers.add(row.supplier)
		if not self.opening_date:
			self.opening_date = nowdate()
		if self.closing_date and self.opening_date and getdate(self.closing_date) < getdate(self.opening_date):
			frappe.throw(_("Closing Date cannot be before Opening Date"))

	def on_update(self) -> None:
		if not self.request or not frappe.db.exists("Requests", self.request):
			return
		if not frappe.get_meta("Requests").has_field("tender"):
			return
		if frappe.db.get_value("Requests", self.request, "tender") != self.name:
			frappe.db.set_value("Requests", self.request, "tender", self.name, update_modified=False)
		from request_center.tender import copy_suppliers_to_request

		copy_suppliers_to_request(self)
