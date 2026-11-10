frappe.query_reports["NEMIS Census"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: "Learner List\nClass Summary\nAge & Gender", default: "Learner List" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "Active\nSuspended\nTransferred\nLeft\nGraduated", default: "Active" },
		{ fieldname: "census_date", label: __("Age On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "missing_only", label: __("Only learners missing census data"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "missing" && data && data.missing) return `<span style="color:var(--red-600)">${value}</span>`;
		return value;
	},
};
