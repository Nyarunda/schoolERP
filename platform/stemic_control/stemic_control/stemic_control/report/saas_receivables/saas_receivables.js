frappe.query_reports["SaaS Receivables"] = {
	filters: [
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "agent", label: __("Agent"), fieldtype: "Link", options: "SaaS Agent" },
	],
};
