frappe.query_reports["Teacher Workload"] = {
	filters: [
		{ fieldname: "school_term", label: __("Term"), fieldtype: "Link", options: "School Term" },
	],
};
