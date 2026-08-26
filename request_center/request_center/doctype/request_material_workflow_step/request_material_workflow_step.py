# Copyright (c) 2026, Hager and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RequestMaterialWorkflowStep(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		branch: DF.Literal["Common", "Inventory", "Purchase"]
		document_name: DF.Data | None
		document_type: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		remarks: DF.SmallText | None
		stage: DF.Data
		step: DF.Int
		step_status: DF.Literal["Pending", "Current", "Done", "Skipped"]
	# end: auto-generated types

	pass
