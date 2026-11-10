// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Homework", {
	setup(frm) {
		frm.set_query("stream", () => ({ filters: { is_active: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.status === "Draft" && !frm.is_new()) {
			frm.add_custom_button(__("Publish to Parents"), () => frm.set_value("status", "Published").then(() => frm.save())).addClass("btn-primary");
		}
		if (frm.doc.status === "Published") {
			frm.add_custom_button(__("Close"), () => frm.set_value("status", "Closed").then(() => frm.save()));
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Get Learners"), () => get_learners(frm), __("Hand-in"));
			frm.add_custom_button(__("Mark All Submitted"), () => mark_all(frm, "Submitted"), __("Hand-in"));
		}
		if (frm.doc.submissions && frm.doc.submissions.length) {
			frm.dashboard.add_indicator(__("{0} of {1} handed in", [frm.doc.done_count, frm.doc.submissions.length]),
				frm.doc.pending_count ? "orange" : "green");
		}
	},
});

function get_learners(frm) {
	if (!frm.doc.stream) return frappe.msgprint(__("Choose the stream first"));
	frappe.call("school_erp.api.homework.stream_students", { stream: frm.doc.stream }).then(({ message }) => {
		const have = new Set((frm.doc.submissions || []).map((r) => r.student));
		(message || []).forEach((s) => { if (!have.has(s.student)) frm.add_child("submissions", { ...s, status: "Pending" }); });
		frm.refresh_field("submissions");
		frm.dirty();
	});
}

function mark_all(frm, status) {
	(frm.doc.submissions || []).forEach((r) => { if (r.status === "Pending") r.status = status; });
	frm.refresh_field("submissions");
	frm.dirty();
}
