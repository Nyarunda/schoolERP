frappe.query_reports["Homework Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("Set From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream" },
		{ fieldname: "subject", label: __("Subject"), fieldtype: "Link", options: "Subject" },
		{ fieldname: "teacher", label: __("Teacher"), fieldtype: "Link", options: "Teacher" },
	],
};
