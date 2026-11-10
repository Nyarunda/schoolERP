// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Sick Bay Visit", {
	student(frm) {
		if (!frm.doc.student) return;
		frappe.db.get_value("Student Health Record", frm.doc.student, ["allergies", "chronic_conditions"]).then(({ message }) => {
			frm.set_value({ allergies: (message && message.allergies) || "", chronic_conditions: (message && message.chronic_conditions) || "" });
		});
	},
	refresh(frm) {
		if (frm.doc.allergies) frm.set_intro(__("Allergies: {0}", [frappe.utils.escape_html(frm.doc.allergies)]), "red");
		if (frm.is_new()) return;
		frm.add_custom_button(__("SMS Parent"), () => frappe.call({ method: "school_erp.api.health.sms_parent_about_visit", args: { name: frm.doc.name }, freeze: true })
			.then(({ message }) => { frappe.show_alert({ message: __("Sent to {0} number(s)", [message.sent]), indicator: "green" }); frm.reload_doc(); }));
		if (["Sent home", "Referred to hospital"].includes(frm.doc.outcome)) {
			frm.add_custom_button(__("Issue Gate Pass"), () => frappe.new_doc("Gate Pass", { student: frm.doc.student, reason: "Medical",
				details: frm.doc.symptoms, sick_bay_visit: frm.doc.name }));
		}
	},
});
