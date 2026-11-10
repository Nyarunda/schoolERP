frappe.query_reports["Paybill Reconciliation"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nReceived\nPosted\nUnmatched\nFailed\nIgnored" },
	],
	formatter: (...a) => school_dash.report_formatter({ status: ["status"] })(...a),
};
