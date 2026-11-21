// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Library Loan", {
	setup(frm) {
		frm.set_query("student", () => ({ filters: { status: "Active" } }));
		frm.set_query("teacher", () => ({ filters: { is_active: 1 } }));
	},
	onload(frm) { load_copies(frm); },
	book(frm) { frm.set_value("accession_no", ""); load_copies(frm); },
	refresh(frm) {
		if (frm.is_new()) return;
		const act = (method, args = {}) => frappe.call({ method: `school_erp.api.library.${method}`, args: { name: frm.doc.name, ...args }, freeze: true })
			.then(({ message }) => { if (message && message.message) frappe.msgprint(message.message); frm.reload_doc(); });
		if (frm.doc.status === "On Loan") {
			frm.add_custom_button(__("Return"), () => frappe.prompt({ fieldname: "condition", label: __("Condition"), fieldtype: "Select",
				options: "Good\nFair\nPoor\nDamaged", default: "Good" }, ({ condition }) => act("return_book", { condition }), __("Return {0}", [frm.doc.book_title]), __("Return"))).addClass("btn-primary");
			frm.add_custom_button(__("Renew"), () => act("renew_loan"));
			frm.add_custom_button(__("Mark Lost"), () => frappe.confirm(__("Mark this copy as lost? The replacement price is charged."), () => act("mark_lost")));
			if (frm.doc.due_date < frappe.datetime.get_today()) frm.set_intro(__("Overdue since {0}", [frappe.datetime.str_to_user(frm.doc.due_date)]), "red");
		}
		const open_fine = frm.doc.fine_amount > 0 && !frm.doc.fine_waived && !frm.doc.fine_invoice && !frm.doc.fine_paid_entry;
		if (open_fine && frm.doc.student) {
			frm.add_custom_button(__("Bill Fine to Fees"), () => act("bill_fine"));
		}
		if (open_fine) {
			frm.add_custom_button(__("Fine Paid"), () => frappe.prompt([
				{ fieldname: "mode", label: __("Paid by"), fieldtype: "Select", options: "Cash\nM-Pesa", default: "Cash", reqd: 1 },
				{ fieldname: "reference", label: __("M-Pesa code"), fieldtype: "Data", depends_on: "eval:doc.mode=='M-Pesa'",
					mandatory_depends_on: "eval:doc.mode=='M-Pesa'" },
			], (v) => act("fine_paid", v), __("Fine of {0} paid", [format_currency(frm.doc.fine_amount)]), __("Record payment")));
		}
		if (frm.doc.fine_paid_entry) {
			frm.set_intro(__("Fine paid by {0} and posted to the ledger ({1}).", [frm.doc.fine_paid_mode, frm.doc.fine_paid_entry]), "green");
		}
	},
});

function load_copies(frm) {
	if (!frm.doc.book || !frm.is_new()) return;
	frappe.call("school_erp.api.library.available_copies", { book: frm.doc.book }).then(({ message }) => {
		frm.set_df_property("accession_no", "options", message || []);
		if (!frm.doc.accession_no && message && message.length) frm.set_value("accession_no", message[0]);
	});
}
