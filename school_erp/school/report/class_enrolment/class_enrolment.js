frappe.query_reports["Class Enrolment"] = {
	filters: [
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "Active\nSuspended\nLeft\nGraduated", default: "Active" },
	],
	add_total_row: 1,
};
