frappe.query_reports["Transport List"] = {
	filters: [
		{ fieldname: "list_type", label: __("List"), fieldtype: "Select", options: "Transport\nLunch", default: "Transport" },
		{ fieldname: "route", label: __("Route"), fieldtype: "Link", options: "Transport Route" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
	],
};
