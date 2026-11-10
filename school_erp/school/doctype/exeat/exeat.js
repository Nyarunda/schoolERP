// Copyright (c) 2026, School ERP and contributors
// Exeat: request -> approve -> gate check-out (who collected) -> gate check-in. Parents get an SMS at each gate step.

frappe.ui.form.on("Exeat", {
	setup(frm) {
		frm.set_query("student", () => ({ filters: { boarding_type: "Boarder", status: "Active" } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		const act = (action, args = {}) => frappe.call({ method: `school_erp.api.boarding.${action}`, args: { name: frm.doc.name, ...args }, freeze: true })
			.then(() => frm.reload_doc());
		const s = frm.doc.status;
		if (s === "Requested") {
			frm.add_custom_button(__("Approve"), () => act("approve_exeat")).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => frappe.prompt({ fieldname: "note", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
				({ note }) => act("reject_exeat", { note }), __("Reject exeat")));
		}
		if (s === "Approved") {
			frm.add_custom_button(__("Check Out at Gate"), () => frappe.prompt([
				{ fieldname: "picked_by_name", label: __("Collected by"), fieldtype: "Data", reqd: 1, default: frm.doc.picked_by_name },
				{ fieldname: "picked_by_relation", label: __("Relationship"), fieldtype: "Select", options: "\nMother\nFather\nGuardian\nSibling\nRelative\nDriver\nOther", default: frm.doc.picked_by_relation },
				{ fieldname: "picked_by_id", label: __("ID No."), fieldtype: "Data", default: frm.doc.picked_by_id },
				{ fieldname: "picked_by_phone", label: __("Phone"), fieldtype: "Data", default: frm.doc.picked_by_phone },
			], (v) => act("check_out", v), __("Check out {0}", [frm.doc.student_name]), __("Check Out"))).addClass("btn-primary");
		}
		if (s === "Out") frm.add_custom_button(__("Check In (Back at School)"), () => act("check_in")).addClass("btn-primary");
		if (["Requested", "Approved"].includes(s)) frm.add_custom_button(__("Cancel Exeat"), () => act("cancel_exeat"));
		if (s === "Out" && frappe.datetime.str_to_obj(frm.doc.expected_return) < new Date()) frm.set_intro(__("Overdue: was due back {0}", [frappe.datetime.str_to_user(frm.doc.expected_return)]), "red");
	},
});
