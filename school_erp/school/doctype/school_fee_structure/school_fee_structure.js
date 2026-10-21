frappe.ui.form.on("School Fee Structure", {
	setup(frm) {
		frm.set_query("fee_type", "items", () => ({ filters: { category: ["not in", ["Transport", "Activity"]] } }));
	},
	refresh(frm) {
		frm.set_intro(__("Transport and Games/Activity fees are set on each Transport Route and School Activity. Lunch is only charged to students marked 'Takes School Lunch'."), "blue");
	},
});

frappe.ui.form.on("Fee Structure Item", {
	amount(frm) {
		frm.set_value("total_amount", (frm.doc.items || []).reduce((t, r) => t + (r.amount || 0), 0));
	},
	items_remove(frm) {
		frm.set_value("total_amount", (frm.doc.items || []).reduce((t, r) => t + (r.amount || 0), 0));
	},
});
