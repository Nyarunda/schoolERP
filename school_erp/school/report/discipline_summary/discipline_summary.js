frappe.query_reports["Discipline Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -3), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: "Class\nCategory\nStudent", default: "Class" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
	],
};
