frappe.query_reports["Agent Commission Statement"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.year_start(), 0), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "agent", label: __("Agent"), fieldtype: "Link", options: "SaaS Agent" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDue\nPaid" },
	],
};
