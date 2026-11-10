frappe.query_reports["Visitor Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "purpose", label: __("Purpose"), fieldtype: "Select", options: "\nParent visit\nOfficial / Ministry\nDelivery\nContractor / Repairs\nInterview\nMeeting\nCollecting a learner\nOther" },
		{ fieldname: "on_premises", label: __("Only visitors still on the premises"), fieldtype: "Check" },
	],
};
