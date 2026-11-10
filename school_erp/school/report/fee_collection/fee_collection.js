frappe.query_reports["Fee Collection"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "mode_of_payment", label: __("Mode"), fieldtype: "Link", options: "Mode of Payment" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "student", label: __("Student"), fieldtype: "Link", options: "Student" },
	],
	onload(report) {
		// quick ranges: the questions a bursar actually asks
		const set = (from, to) => { report.set_filter_value({ from_date: from, to_date: to }); };
		const today = frappe.datetime.get_today();
		report.page.add_inner_button(__("Today"), () => set(today, today), __("Period"));
		report.page.add_inner_button(__("This week"), () => set(frappe.datetime.week_start(), today), __("Period"));
		report.page.add_inner_button(__("This month"), () => set(frappe.datetime.month_start(), today), __("Period"));
		report.page.add_inner_button(__("This year"), () => set(frappe.datetime.year_start(), today), __("Period"));
	},
};
