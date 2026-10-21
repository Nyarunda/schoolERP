frappe.query_reports["Fee Collection"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "mode_of_payment", label: __("Mode"), fieldtype: "Link", options: "Mode of Payment" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
	],
};
