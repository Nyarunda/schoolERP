frappe.query_reports["Driver Check-in Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -7), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "driver", label: __("Driver"), fieldtype: "Link", options: "Staff Member" },
		{ fieldname: "date_for_missing", label: __("Show who has not checked in on"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && (data.state === "NOT CHECKED IN" || (column.fieldname === "has_issues" && data.has_issues) || (column.fieldname === "late" && data.late)))
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		return value;
	},
};
