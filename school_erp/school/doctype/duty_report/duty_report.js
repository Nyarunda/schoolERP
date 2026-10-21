// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Duty Report", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.staff_member) {
			frappe.call("school_erp.api.staff.my_staff_record").then((r) => r.message && frm.set_value("staff_member", r.message));
		}
		if (frm.is_new() && !frm.doc.arrival_time) {
			frm.set_value("arrival_time", frappe.datetime.now_time());
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.set_intro(__("Submit before you leave. The Head Teacher receives it immediately."), "blue");
			frm.add_custom_button(__("Record a discipline incident"), () => frappe.new_doc("Discipline Incident", { reported_by: frm.doc.staff_member }));
		}
	},
});
