frappe.query_reports["VAT Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.month_start(), -1), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.month_start(), -1), reqd: 1 },
	],
	formatter: (...a) => school_dash.report_formatter({ negative: ["payable"] })(...a),
};
