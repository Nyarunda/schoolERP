frappe.query_reports["Admissions Pipeline"] = {
	filters: [
		{ fieldname: "from_date", label: __("Applied From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -6) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "applying_for_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "intake_term", label: __("Intake Term"), fieldtype: "Link", options: "School Term" },
		{ fieldname: "source", label: __("Source"), fieldtype: "Select", options: "\nOffice\nWeb Form\nWalk-in\nPhone" },
	],
};
