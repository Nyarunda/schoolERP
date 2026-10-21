frappe.ui.form.on("Transport Route", {
	setup(frm) {
		frm.set_query("fee_type", () => ({ filters: { category: "Transport" } }));
	},
});
