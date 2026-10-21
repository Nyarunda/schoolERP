frappe.listview_settings["School Fee Structure"] = {
	onload(list) {
		list.page.add_inner_button(__("Copy a term to another term"), () => {
			frappe.prompt(
				[
					{ fieldname: "from_term", label: __("From Term"), fieldtype: "Link", options: "School Term", reqd: 1 },
					{ fieldname: "to_term", label: __("To Term"), fieldtype: "Link", options: "School Term", reqd: 1 },
					{ fieldname: "increase_percent", label: __("Increase fees by (%)"), fieldtype: "Float", default: 0 },
					{ fieldname: "round_to", label: __("Round to nearest"), fieldtype: "Currency", default: 0 },
				],
				(v) => frappe.call({ method: "school_erp.api.billing.copy_fee_structures", args: v, freeze: true }).then(({ message: m }) => {
					frappe.msgprint(__("Created {0} fee structure(s).", [m.created.length]));
					list.refresh();
				}),
				__("Copy fee structures"),
			);
		});
		list.page.add_inner_button(__("Fees by Class and Term"), () => frappe.set_route("query-report", "Fee Structure Matrix"));
	},
};
