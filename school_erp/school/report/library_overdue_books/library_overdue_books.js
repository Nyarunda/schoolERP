frappe.query_reports["Library Overdue Books"] = {
	filters: [
		{ fieldname: "borrower_type", label: __("Borrower"), fieldtype: "Select", options: "\nStudent\nTeacher" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
	],
};
