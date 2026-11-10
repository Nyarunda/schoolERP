// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Gate Pass", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Out") {
			frm.add_custom_button(__("Mark Returned"), () => frappe.call({ method: "school_erp.api.health.gate_pass_returned", args: { name: frm.doc.name } })
				.then(() => frm.reload_doc())).addClass("btn-primary");
		}
	},
});
