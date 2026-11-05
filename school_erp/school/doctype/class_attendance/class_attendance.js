// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Class Attendance", {
	setup(frm) {
		frm.set_query("stream", () => ({ filters: { is_active: 1 } }));
	},
	refresh(frm) {
		frm.add_custom_button(__("Open Class Register"), () =>
			frappe.set_route("class-register", { stream: frm.doc.stream || "", date: frm.doc.attendance_date || "" }));
		if (!frm.is_new()) {
			frm.dashboard.add_indicator(__("{0}% attendance", [frm.doc.attendance_percent || 0]), frm.doc.absent ? "orange" : "green");
			frm.dashboard.add_indicator(__("Present {0} · Absent {1} · Late {2} · Excused {3}",
				[frm.doc.present, frm.doc.absent, frm.doc.late, frm.doc.excused]), "gray");
		}
	},
	stream(frm) {
		if (!frm.doc.stream || (frm.doc.students || []).length) return;
		frm.call({ doc: frm.doc, method: "get_students" }).then(() => frm.refresh_field("students"));
	},
});
