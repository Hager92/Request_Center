frappe.listview_settings["Requests"] = {
	add_fields: [
		"request_date",
		"status",
		"category",
		"approval_status_summary",
		"current_approval_level",
		"current_approver",
		"fulfillment_stage",
		"inventory_check_result",
	],
	hide_name_column: false,
	onload: function (listview) {
		listview.page.set_primary_action(__("Request Center"), () => {
			frappe.set_route("request-center-home");
		});
	},
	get_indicator: function (doc) {
		const colors = {
			Draft: "gray",
			"Need Approval": "orange",
			"Pending Approval": "orange",
			"Pending Manager": "orange",
			"Pending Department": "orange",
			Approved: "green",
			Rejected: "red",
			Completed: "blue",
			"In Progress": "yellow",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
	formatters: {
		days_elapsed: function (value, df, doc) {
			if (!doc.request_date) {
				return value || 0;
			}
			return Math.max(
				0,
				frappe.datetime.get_diff(frappe.datetime.now_datetime(), doc.request_date)
			);
		},
	},
};
