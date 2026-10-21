frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.student && frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0) {
			frm.add_custom_button(__("Record Fee Payment"), () => frappe.new_doc("Fee Payment", { student: frm.doc.student }), __("Create"));
		}
	},
});
