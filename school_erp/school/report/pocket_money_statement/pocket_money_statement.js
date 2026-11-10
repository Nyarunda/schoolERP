frappe.query_reports["Pocket Money Statement"] = {
	filters: [
		{ fieldname: "student", label: __("Learner"), fieldtype: "Link", options: "Student" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
