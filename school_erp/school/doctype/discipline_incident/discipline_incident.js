// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Discipline Incident", {
	refresh(frm) {
		const colors = { Open: "orange", "Under Review": "blue", Resolved: "green" };
		if (!frm.is_new()) frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status]);
		if (frm.is_new()) return;
		const has_sms = ((frappe.boot.school_erp || {}).modules || []).includes("messaging");
		if (has_sms) {
			frm.add_custom_button(frm.doc.parent_notified ? __("SMS Parent Again") : __("SMS Parent"), () =>
				frappe.confirm(__("Send an SMS about this incident to the student's parents/guardians?"), () =>
					frappe.call({ method: "school_erp.api.welfare.notify_parent_of_incident", args: { name: frm.doc.name }, freeze: true })
						.then(({ message }) => { frappe.msgprint(__("SMS sent to {0} number(s)", [message.sent])); frm.reload_doc(); })));
		}
		frm.add_custom_button(__("Student's History"), () => frappe.set_route("List", "Discipline Incident", { student: frm.doc.student }));
	},
});
