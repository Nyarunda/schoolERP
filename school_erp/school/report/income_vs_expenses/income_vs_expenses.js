frappe.query_reports["Income vs Expenses"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.year_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
	add_total_row: 1,
	formatter: (...a) => school_dash.report_formatter({ negative: ["net"] })(...a),
};
