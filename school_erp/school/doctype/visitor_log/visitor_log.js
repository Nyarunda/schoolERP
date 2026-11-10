// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Visitor Log", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "On premises") {
			frm.add_custom_button(__("Sign Out"), () => frappe.call({ method: "school_erp.api.health.sign_out_visitor", args: { name: frm.doc.name } })
				.then(() => frm.reload_doc())).addClass("btn-primary");
		}
	},
});
