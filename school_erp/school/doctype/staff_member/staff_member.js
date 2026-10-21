// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Staff Member", {
	setup(frm) {
		frm.set_query("reports_to", () => ({ filters: { status: ["!=", "Left"], name: ["!=", frm.doc.name || ""] } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Apply Leave"), () => frappe.new_doc("Leave Application", { staff_member: frm.doc.name }), __("Create"));
		frm.add_custom_button(__("Leave History"), () => frappe.set_route("List", "Leave Application", { staff_member: frm.doc.name }), __("View"));
		if (frm.doc.staff_type === "Driver") {
			frm.add_custom_button(__("Driver Logs"), () => frappe.set_route("List", "Driver Daily Log", { driver: frm.doc.name }), __("View"));
		}
		if (frm.doc.staff_type === "Teaching") {
			frm.add_custom_button(__("Duty Reports"), () => frappe.set_route("List", "Duty Report", { staff_member: frm.doc.name }), __("View"));
		}
		frappe.call("school_erp.api.staff.leave_balances", { staff_member: frm.doc.name }).then(({ message }) => {
			(message || []).filter((r) => r.entitled).forEach((r) => {
				frm.dashboard.add_indicator(`${r.leave_type}: ${r.balance} ${__("left")}`, r.balance > 0 ? "green" : "red");
			});
		});
		if (!frm.doc.user) {
			frm.set_intro(__("Link a login (User) so this person can apply for leave and file reports themselves."), "blue");
		}
	},
});
