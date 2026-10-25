const PORTAL_STATUS_COLOR = {
	"Active": "var(--green-600)", "Never Logged In": "var(--blue-600)", "No Login": "var(--orange-600)",
	"Login Disabled": "var(--orange-600)", "Missing Parent Role": "var(--orange-600)", "No Contact": "var(--red-600)",
};

frappe.query_reports["Parent Portal Access"] = {
	filters: [
		{ fieldname: "status", label: __("Portal Access"), fieldtype: "Select",
			options: ["", "Active", "Never Logged In", "No Login", "Login Disabled", "Missing Parent Role", "No Contact"] },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && PORTAL_STATUS_COLOR[data.status])
			value = `<span style="color:${PORTAL_STATUS_COLOR[data.status]};font-weight:600">● ${value}</span>`;
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__("Give All Parents Portal Access"), () =>
			frappe.confirm(__("Create parent portal logins for the guardians of every active student and SMS them their password?"), () =>
				frappe.call({ method: "school_erp.api.portal.give_portal_access", args: { all_students: 1 }, freeze: true, freeze_message: __("Creating logins...") })
					.then(({ message: m }) => {
						frappe.msgprint(__("{0} new parent logins created, {1} guardians linked, {2} without a phone or email.", [m.new_logins, m.linked, m.without_contact]));
						report.refresh();
					})));
		report.page.add_inner_button(__("Open Parent Portal"), () => window.open("/parent"));
	},
};
