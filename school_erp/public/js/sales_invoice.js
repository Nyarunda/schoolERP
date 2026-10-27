frappe.ui.form.on("Sales Invoice", {
	// ERPNext's controller sets its customer search in its own onload, after ours: add the student filter once the
	// form has finished loading, and again on refresh in case it was reset
	onload_post_render: (frm) => school_erp.exclude_students(frm, "customer", (doc) => !doc.student),
	refresh(frm) {
		school_erp.exclude_students(frm, "customer", (doc) => !doc.student);
		if (frm.doc.student && frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0) {
			frm.add_custom_button(__("Record Fee Payment"), () => frappe.new_doc("Fee Payment", { student: frm.doc.student }), __("Create"));
		}
	},
});
