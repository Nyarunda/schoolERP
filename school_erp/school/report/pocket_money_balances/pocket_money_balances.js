frappe.query_reports["Pocket Money Balances"] = {
	filters: [
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "frozen_only", label: __("Only frozen accounts"), fieldtype: "Check" },
	],
};
