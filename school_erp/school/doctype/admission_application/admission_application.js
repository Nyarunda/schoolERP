// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Admission Application", {
	setup(frm) {
		frm.set_query("assigned_stream", () => ({ filters: { is_active: 1, school_class: frm.doc.applying_for_class || "" } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.student) {
			frm.set_intro(__("Admitted as {0}", [`<a href="/app/student/${encodeURIComponent(frm.doc.student)}">${frm.doc.student}</a>`]), "green");
			return;
		}
		if (["Offered", "Accepted"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Admit as Student"), () => admit(frm)).addClass("btn-primary");
		}
		const next = {
			"Received": ["Under Review", "Interview Scheduled", "Offered", "Rejected"],
			"Under Review": ["Interview Scheduled", "Offered", "Rejected"],
			"Interview Scheduled": ["Offered", "Rejected"],
			"Offered": ["Accepted", "Withdrawn"],
			"Rejected": ["Under Review"],
			"Withdrawn": ["Under Review"],
		}[frm.doc.status] || [];
		next.forEach((s) => frm.add_custom_button(__(s), () => {
			if (s === "Interview Scheduled" && !frm.doc.interview_date) {
				frappe.prompt({ fieldname: "when", label: __("Interview date and time"), fieldtype: "Datetime", reqd: 1 }, ({ when }) => {
					frm.set_value({ interview_date: when, status: s }).then(() => frm.save());
				}, __("Schedule interview"));
				return;
			}
			if (s === "Rejected" && !(frm.doc.decision_notes || "").trim()) {
				frappe.prompt({ fieldname: "why", label: __("Reason (internal)"), fieldtype: "Small Text", reqd: 1 }, ({ why }) => {
					frm.set_value({ decision_notes: why, status: s }).then(() => frm.save());
				}, __("Not successful"));
				return;
			}
			frm.set_value("status", s).then(() => frm.save());
		}, __("Move to")));
	},
});

function admit(frm) {
	frappe.prompt([
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream", reqd: 1, default: frm.doc.assigned_stream,
			get_query: () => ({ filters: { is_active: 1, school_class: frm.doc.applying_for_class || "" } }) },
	], ({ stream }) => {
		frappe.call({ method: "school_erp.api.admissions.admit", args: { application: frm.doc.name, stream }, freeze: true })
			.then(({ message }) => {
				frappe.show_alert({ message: __("Admitted as {0}", [message.student]), indicator: "green" });
				frm.reload_doc();
			});
	}, __("Admit {0}", [frm.doc.applicant_name]), __("Admit"));
}
