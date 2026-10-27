// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("School Expense", {
	setup(frm) {
		frm.set_query("expense_category", () => ({ filters: { is_active: 1 } }));
		frm.set_query("withholding_tax_type", () => ({ filters: { is_active: 1 } }));
	},

	onload(frm) {
		// Tax fields only matter if the school uses them (School Settings > Tax)
		frappe.db.get_value("School Settings", "School Settings", ["vat_registered", "withhold_tax", "vat_withholding_agent"]).then(({ message: t }) => {
			frm.toggle_display("supplier_charged_vat", !!(t.vat_registered || t.vat_withholding_agent));
			frm.toggle_display("withholding_tax_type", !!t.withhold_tax);
		});
	},

	refresh(frm) {
		const colors = { Draft: "gray", "Pending Approval": "orange", "Pending Final Approval": "orange", Approved: "green", Rejected: "red", Cancelled: "gray" };
		if (!frm.is_new()) frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status]);
		if (frm.doc.docstatus !== 0 || frm.is_new()) {
			if (frm.doc.journal_entry) {
				frm.add_custom_button(__("Journal Entry"), () => frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry));
			}
			return;
		}
		if (frm.doc.status === "Draft") {
			frm.set_intro(__("Save, then choose Actions → Send for Approval."), "blue");
		} else if (["Pending Approval", "Pending Final Approval"].includes(frm.doc.status)) {
			const level = frm.doc.status === "Pending Final Approval" ? __("final") : __("first");
			frm.set_intro(__("Waiting for the {0} approval ({1} approval(s) needed for this amount). Approvers use the Actions menu.", [level, frm.doc.levels_required]), "orange");
		} else if (frm.doc.status === "Rejected") {
			frm.set_intro(__("Rejected: {0}. Edit if needed, then choose Actions → Resend.", [frm.doc.rejection_reason || ""]), "red");
		}
	},

	// Frappe Workflow hook: ask for the reason before a rejection
	before_workflow_action(frm) {
		return school_dash.reason_before_reject(frm, "rejection_reason");
	},
});

