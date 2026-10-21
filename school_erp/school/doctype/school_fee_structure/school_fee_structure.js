frappe.ui.form.on("School Fee Structure", {
	setup(frm) {
		frm.set_query("fee_type", "items", () => ({ filters: { category: ["not in", ["Transport", "Activity"]] } }));
	},
	refresh(frm) {
		frm.set_intro(__("Fees can differ per class and per term: make one structure per class (or a general one for all classes) for each term. Transport and Games/Activity fees are set on each Transport Route and School Activity. Lunch is only charged to students marked 'Takes School Lunch'."), "blue");
		if (!frm.is_new()) {
			frm.add_custom_button(__("Copy this term's fees to another term"), () => copy_dialog(frm.doc.school_term));
		}
	},
});

frappe.ui.form.on("Fee Structure Item", {
	amount(frm) { set_total(frm); },
	items_remove(frm) { set_total(frm); },
});

function set_total(frm) {
	frm.set_value("total_amount", (frm.doc.items || []).reduce((t, r) => t + (r.amount || 0), 0));
}

function copy_dialog(from_term) {
	frappe.prompt(
		[
			{ fieldname: "from_term", label: __("From Term"), fieldtype: "Link", options: "School Term", default: from_term, reqd: 1 },
			{ fieldname: "to_term", label: __("To Term"), fieldtype: "Link", options: "School Term", reqd: 1 },
			{ fieldname: "increase_percent", label: __("Increase fees by (%)"), fieldtype: "Float", default: 0 },
			{ fieldname: "round_to", label: __("Round to nearest"), fieldtype: "Currency", default: 0, description: __("e.g. 50 or 100; 0 = no rounding") },
		],
		(v) => frappe.call({ method: "school_erp.api.billing.copy_fee_structures", args: v, freeze: true }).then(({ message: m }) => {
			frappe.msgprint(__("Created {0} fee structure(s) for {1}.", [m.created.length, v.to_term]) +
				(m.skipped.length ? "<br>" + __("Skipped (already exist): {0}", [m.skipped.join(", ")]) : ""));
			frappe.set_route("List", "School Fee Structure", { school_term: v.to_term });
		}),
		__("Copy fee structures (every class) to another term"),
		__("Copy"),
	);
}
