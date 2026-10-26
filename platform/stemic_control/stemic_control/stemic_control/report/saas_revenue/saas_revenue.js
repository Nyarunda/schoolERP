frappe.query_reports["SaaS Revenue"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.year_start(), 0), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "plan", label: __("Plan"), fieldtype: "Link", options: "SaaS Plan" },
	],
};
