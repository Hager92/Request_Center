frappe.pages["request-center-home"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Request Center"),
		single_column: true,
	});

	page.set_secondary_action(__("Refresh"), function () {
		load_portal();
	});

	const $body = $(`
		<div class="request-center-home">
			<p class="request-center-home__overview">
				${__("Create, configure, approve, and track employee requests. Open a Request Type below.")}
			</p>
			<div class="request-center-home__pending"></div>
			<div class="request-center-home__grid"></div>
			<div class="request-center-home__mine">
				<h5 class="request-center-home__section-title">${__("My Requests")}</h5>
				<p class="text-muted request-center-home__section-hint">
					${__("Request status, approval progress, and pending actions")}
				</p>
				<div class="request-center-home__mine-table"></div>
			</div>
		</div>
	`).appendTo(page.body);

	const $grid = $body.find(".request-center-home__grid");
	const $mine = $body.find(".request-center-home__mine-table");
	const $pending = $body.find(".request-center-home__pending");
	let portalData = { types: [], counts: {}, names_by_type: {}, to_review: [], my_requests: [] };

	$body.on("click", ".btn-new-request", function (e) {
		e.preventDefault();
		e.stopPropagation();
		const requestType = $(this).closest(".request-type-card").attr("data-request-type");
		if (!requestType) {
			return;
		}
		frappe.new_doc("Requests", { request_type: requestType });
	});

	$body.on("click", ".btn-to-review", function (e) {
		e.preventDefault();
		e.stopPropagation();
		const requestType = $(this).closest(".request-type-card").attr("data-request-type");
		open_to_review(requestType);
	});

	$body.on("click", ".request-center-home__pending-btn", function () {
		open_to_review();
	});

	$body.on("click", ".request-portal-row", function () {
		const name = $(this).attr("data-name");
		if (name) {
			frappe.set_route("Form", "Requests", name);
		}
	});

	function load_portal() {
		frappe.call({
			method: "request_center.api.requests.get_portal_data",
			freeze: true,
			callback: function (r) {
				portalData = r.message || portalData;
				render_cards();
				render_pending();
				render_my_requests();
			},
		});
	}

	function render_cards() {
		const types = portalData.types || [];
		const counts = portalData.counts || {};
		$grid.empty();

		if (!types.length) {
			$grid.html(`<p class="text-muted">${__("No active Request Types")}</p>`);
			return;
		}

		types.forEach((t) => {
			const name = frappe.utils.escape_html(t.name || "");
			const count = counts[t.name] || 0;
			const countClass = count ? "has-count" : "";
			const categoryClass = category_class(t.category);
			$grid.append(`
				<div class="request-type-card" data-request-type="${name}">
					<div class="request-type-card__icon ${categoryClass}">${card_icon_html(t.icon)}</div>
					<div class="request-type-card__body">
						<div class="request-type-card__title">${name}</div>
						<div class="request-type-card__actions">
							<button class="btn-new-request" type="button">${__("New Request")}</button>
							<button class="btn-to-review ${countClass}" type="button">
								${__("To Review")}: ${count}
							</button>
						</div>
					</div>
				</div>
			`);
		});
	}

	function card_icon_html(icon) {
		if (icon) {
			return frappe.utils.icon(icon, "xl");
		}
		return frappe.utils.icon("small-file", "xl");
	}

	function category_class(category) {
		const map = {
			"Service Request": "is-service",
			"Material Request": "is-material",
			"Disbursement Request": "is-disbursement",
			"Other Requests": "is-other",
		};
		return map[category] || "is-other";
	}

	function render_pending() {
		const total = (portalData.to_review || []).length;
		if (!total) {
			$pending.hide().empty();
			return;
		}
		$pending.show().html(`
			<button type="button" class="request-center-home__pending-btn">
				${__("Pending actions")}: ${total} ${__("to review")}
			</button>
		`);
	}

	function render_my_requests() {
		const rows = portalData.my_requests || [];
		if (!rows.length) {
			$body.find(".request-center-home__mine").toggle(true);
			$mine.html(
				`<p class="text-muted">${__("You have no requests yet. Choose a Request Type and click New Request.")}</p>`
			);
			return;
		}
		$body.find(".request-center-home__mine").toggle(true);
		let html = `<div class="table-responsive"><table class="table table-hover request-center-home__table">
			<thead><tr>
				<th>${__("Request")}</th>
				<th>${__("Request Type")}</th>
				<th>${__("Request Status")}</th>
				<th>${__("Current Approval Level")}</th>
				<th>${__("Current Approver")}</th>
				<th>${__("Final Result")}</th>
			</tr></thead><tbody>`;
		rows.forEach((row) => {
			html += `<tr class="request-portal-row" data-name="${frappe.utils.escape_html(row.name)}">
				<td>${frappe.utils.escape_html(row.name)}</td>
				<td>${frappe.utils.escape_html(row.request_type || "")}</td>
				<td>${frappe.utils.escape_html(row.status || "")}</td>
				<td>${frappe.utils.escape_html(row.current_approval_level || "—")}</td>
				<td>${frappe.utils.escape_html(row.current_approver || "—")}</td>
				<td>${frappe.utils.escape_html(final_result_label(row))}</td>
			</tr>`;
		});
		html += "</tbody></table></div>";
		$mine.html(html);
	}

	function open_to_review(requestType) {
		const rows = requestType
			? (portalData.to_review || []).filter((row) => row.request_type === requestType)
			: portalData.to_review || [];
		if (!rows.length) {
			frappe.show_alert({
				message: requestType
					? __("No requests to review for {0}", [requestType])
					: __("No pending actions"),
				indicator: "blue",
			});
			return;
		}

		const title = requestType
			? __("To Review — {0}", [requestType])
			: __("Pending actions");

		const showType = !requestType;
		let html = `<p class="text-muted">${__("Open a request to review it, then Approve or Reject.")}</p>
			<div class="table-responsive"><table class="table table-hover">
			<thead><tr>
				<th>${__("Request")}</th>
				${showType ? `<th>${__("Request Type")}</th>` : ""}
				<th>${__("Request Status")}</th>
				<th>${__("Current Approval Level")}</th>
				<th>${__("Current Approver")}</th>
			</tr></thead><tbody>`;
		rows.forEach((row) => {
			html += `<tr class="request-portal-review-row" data-name="${frappe.utils.escape_html(row.name)}" style="cursor:pointer">
				<td>${frappe.utils.escape_html(row.name)}</td>
				${showType ? `<td>${frappe.utils.escape_html(row.request_type || "")}</td>` : ""}
				<td>${frappe.utils.escape_html(row.status || "")}</td>
				<td>${frappe.utils.escape_html(row.current_approval_level || "—")}</td>
				<td>${frappe.utils.escape_html(row.current_approver || "—")}</td>
			</tr>`;
		});
		html += "</tbody></table></div>";

		const dialog = new frappe.ui.Dialog({
			title: title,
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "list_html" }],
		});
		dialog.fields_dict.list_html.$wrapper.html(html);
		dialog.$wrapper.on("click", ".request-portal-review-row", function () {
			const name = $(this).attr("data-name");
			dialog.hide();
			if (name) {
				frappe.set_route("Form", "Requests", name);
			}
		});
		dialog.show();
	}

	function final_result_label(row) {
		if (row.status === "Rejected") {
			return __("Rejected");
		}
		if (row.status === "Completed") {
			return __("Completed");
		}
		if (row.status === "Approved") {
			return __("Approved");
		}
		if (row.status === "In Progress") {
			return row.fulfillment_stage || __("In Progress");
		}
		if (
			["Need Approval", "Pending Approval", "Pending Manager", "Pending Department"].includes(
				row.status
			)
		) {
			return __("Pending");
		}
		if (row.status === "Draft") {
			return __("Draft");
		}
		return row.status || "—";
	}

	wrapper.request_portal_load = load_portal;
	load_portal();
};

frappe.pages["request-center-home"].on_page_show = function (wrapper) {
	if (wrapper.request_portal_load) {
		wrapper.request_portal_load();
	}
};
