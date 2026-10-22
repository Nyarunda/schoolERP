// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Report Card", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.page.set_indicator(__(frm.doc.status), frm.doc.status === "Published" ? "green" : "orange");
		frm.add_custom_button(__("Download PDF"), () =>
			window.open(`/api/method/school_erp.api.exams.download_report_card?name=${encodeURIComponent(frm.doc.name)}`));
		frm.dashboard.add_indicator(__("Mean {0} ({1}%)", [frm.doc.mean_grade, (frm.doc.mean_percent || 0).toFixed(1)]), "blue");
		frm.dashboard.add_indicator(__("Position {0} / {1}", [frm.doc.stream_position, frm.doc.stream_size]), "gray");
	},
});
