frappe.query_reports["Sick Bay Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: "Visits\nFrequent Visitors", default: "Visits" },
		{ fieldname: "min_visits", label: __("At Least (visits)"), fieldtype: "Int", default: 3, depends_on: "eval:doc.view=='Frequent Visitors'" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "outcome", label: __("Outcome"), fieldtype: "Select", options: "\nReturned to class\nRested in sick bay\nSent home\nReferred to hospital" },
	],
};
