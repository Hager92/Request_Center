// Copyright (c) 2026, Hager and contributors
// For license information, please see license.txt

(function () {
	function is_request_center_workspace() {
		const route = frappe.get_route() || [];
		if (route[0] !== "Workspaces") {
			return false;
		}
		const name = decodeURIComponent(route[1] || "").replace(/-/g, " ");
		return name.toLowerCase() === "request center";
	}

	function open_request_portal() {
		if (!is_request_center_workspace()) {
			return;
		}
		frappe.set_route("request-center-home");
	}

	frappe.router.on("change", open_request_portal);
	$(document).on("app_ready", open_request_portal);

	$(document).on("app_ready", function () {
		if (!frappe.ui.form.States || frappe.ui.form.States.prototype._request_center_unfreeze) {
			return;
		}
		frappe.ui.form.States.prototype.handle_workflow_action = function (transition) {
			const me = this;
			frappe.dom.freeze();
			me.frm.selected_workflow_action = transition.action;
			me.frm.script_manager
				.trigger("before_workflow_action")
				.then(() => {
					return frappe
						.xcall("frappe.model.workflow.apply_workflow", {
							doc: me.frm.doc,
							action: transition.action,
						})
						.then((doc) => {
							frappe.model.sync(doc);
							me.frm.refresh();
							me.frm.selected_workflow_action = null;
							me.frm.script_manager.trigger("after_workflow_action");
						});
				})
				.catch(() => {
					me.frm.selected_workflow_action = null;
				})
				.finally(() => {
					frappe.dom.unfreeze();
				});
		};
		frappe.ui.form.States.prototype._request_center_unfreeze = true;
	});
})();
