frappe.query_reports["Expense Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "expense_category", label: __("Category"), fieldtype: "Link", options: "Expense Category" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nPending Approval\nPending Final Approval\nApproved\nRejected" },
	],
	formatter: (...a) => school_dash.report_formatter({ status: ["status"] })(...a),
};
