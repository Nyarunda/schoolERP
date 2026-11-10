// Copyright (c) 2026, School ERP and contributors

frappe.query_reports["Attendance Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream" },
		{ fieldname: "below", label: __("Only below (%)"), fieldtype: "Float", description: __("e.g. 90 to list students who need follow-up") },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "percent" && data && data.percent != null && data.percent < 90) value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		return value;
	},
};
