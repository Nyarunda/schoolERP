// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("School Notice", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(__("Staff in the chosen audience get a notification (and an SMS if ticked) as soon as you save. It shows on their Staff Room dashboard until 'Show Until'."), "blue");
			return;
		}
		if (frm.doc.audience_count) {
			frm.dashboard.add_indicator(__("{0} of {1} acknowledged", [frm.doc.acknowledged_count || 0, frm.doc.audience_count]),
				frm.doc.acknowledged_count >= frm.doc.audience_count ? "green" : "orange");
		}
		const acked = (frm.doc.acknowledgements || []).some((a) => a.user === frappe.session.user);
		if (!acked) {
			frm.add_custom_button(__("Got it"), () => frappe.call("school_erp.school.doctype.school_notice.school_notice.acknowledge", { name: frm.doc.name }).then(() => frm.reload_doc()));
		}
	},
});
