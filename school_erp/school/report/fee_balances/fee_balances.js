frappe.query_reports["Fee Balances"] = {
	filters: [
		{ fieldname: "school_term", label: __("Term"), fieldtype: "Link", options: "School Term" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{
			fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream",
			get_query: () => {
				const cls = frappe.query_report.get_filter_value("school_class");
				return cls ? { filters: { school_class: cls } } : {};
			},
		},
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nActive\nSuspended\nTransferred\nLeft\nGraduated", default: "Active" },
		{ fieldname: "only_with_balance", label: __("Only students who owe"), fieldtype: "Check", default: 1 },
		{ fieldname: "min_balance", label: __("Minimum balance"), fieldtype: "Currency" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "balance" && data && data.balance > 0) {
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		}
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__("Message these parents"), () => {
			const f = report.get_values();
			frappe.new_doc("School Message", {
				audience: "Students with a balance",
				school_class: f.school_class,
				stream: f.stream,
				min_balance: f.min_balance,
			});
		});
	},
};
