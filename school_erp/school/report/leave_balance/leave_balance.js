frappe.query_reports["Leave Balance"] = {
	filters: [
		{ fieldname: "year", label: __("Year"), fieldtype: "Int", default: new Date().getFullYear() },
		{ fieldname: "staff_type", label: __("Staff Type"), fieldtype: "Select", options: "\nTeaching\nNon-Teaching\nDriver\nAdministration\nSupport" },
	],
};
