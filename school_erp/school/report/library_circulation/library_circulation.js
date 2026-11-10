frappe.query_reports["Library Circulation"] = {
	filters: [
		{ fieldname: "from_date", label: __("Issued From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: "Book\nCategory\nClass", default: "Book" },
	],
};
