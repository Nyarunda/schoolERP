frappe.query_reports["Fee Structure Matrix"] = {
	filters: [
		{ fieldname: "school_year", label: __("School Year"), fieldtype: "Link", options: "School Year" },
	],
	onload(report) {
		report.page.add_inner_button(__("Copy fees to another term"), () => frappe.set_route("List", "School Fee Structure"));
	},
};
