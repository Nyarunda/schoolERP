frappe.ui.form.on("School Activity", {
	setup(frm) {
		frm.set_query("fee_type", () => ({ filters: { category: "Activity" } }));
	},
});
