frappe.query_reports["Exeat Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("Leaving From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nRequested\nApproved\nOut\nReturned\nRejected\nCancelled" },
		{ fieldname: "dormitory", label: __("Dormitory"), fieldtype: "Link", options: "Dormitory" },
		{ fieldname: "out_now", label: __("Only learners out now"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.overdue && ["student_name", "expected_return"].includes(column.fieldname)) return `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		return value;
	},
};
