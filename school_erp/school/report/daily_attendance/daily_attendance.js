// Copyright (c) 2026, School ERP and contributors

frappe.query_reports["Daily Attendance"] = {
	filters: [
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "taken" && data) value = data.taken ? `<span style="color:var(--green-600)">✓ ${__("Taken")}</span>` : `<span style="color:var(--red-600);font-weight:600">${__("Not taken")}</span>`;
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__("Take a register"), () => frappe.set_route("class-register", { date: report.get_filter_value("date") }));
	},
};
