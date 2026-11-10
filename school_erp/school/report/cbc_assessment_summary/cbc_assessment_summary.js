frappe.query_reports["CBC Assessment Summary"] = {
	filters: [
		{ fieldname: "school_term", label: __("Term"), fieldtype: "Link", options: "School Term" },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: "Learning Area\nStrand\nStream", default: "Learning Area" },
		{ fieldname: "school_class", label: __("Grade"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream" },
		{ fieldname: "subject", label: __("Learning Area"), fieldtype: "Link", options: "Subject" },
	],
};
