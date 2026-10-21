frappe.query_reports["Staff On Leave"] = {
	filters: [
		{ fieldname: "date", label: __("On Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
