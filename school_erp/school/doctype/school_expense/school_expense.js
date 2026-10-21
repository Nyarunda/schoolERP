// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("School Expense", {
	setup(frm) {
		frm.set_query("expense_category", () => ({ filters: { is_active: 1 } }));
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
		frm.page.clear_primary_action();
		if (frm.doc.status === "Draft") {
			frm.add_custom_button(__("Send for Approval"), () => {
				if (frm.is_dirty()) return frappe.msgprint(__("Save first"));
				frappe.call({ method: "school_erp.api.expenses.request_approval", args: { name: frm.doc.name }, freeze: true })
					.then(() => { frappe.show_alert({ message: __("Sent for approval"), indicator: "green" }); frm.reload_doc(); });
			}).addClass("btn-primary");
		}
		if (["Pending Approval", "Pending Final Approval"].includes(frm.doc.status)) {
			const level = frm.doc.status === "Pending Final Approval" ? __("final") : __("first");
			frm.set_intro(__("Waiting for the {0} approval. {1} approval(s) needed for this amount.", [level, frm.doc.levels_required]), "orange");
			frm.add_custom_button(__("Approve"), () => decide(frm, "Approved")).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => decide(frm, "Rejected")).addClass("btn-danger");
		}
	},
});

function decide(frm, action) {
	frappe.prompt(
		{ fieldname: "comment", label: action === "Rejected" ? __("Reason") : __("Comment (optional)"), fieldtype: "Small Text", reqd: action === "Rejected" },
		(v) => frappe.call({ method: "school_erp.api.expenses.decide", args: { name: frm.doc.name, action, comment: v.comment }, freeze: true })
			.then(({ message }) => { frappe.show_alert({ message: __("Status: {0}", [__(message)]), indicator: "blue" }); frm.reload_doc(); }),
		action === "Approved" ? __("Approve expense") : __("Reject expense"),
	);
}
