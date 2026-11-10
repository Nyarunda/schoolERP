// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("CBC Progress Report", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Download PDF"), () => {
			window.open(`/api/method/school_erp.api.cbc.download_progress_report?name=${encodeURIComponent(frm.doc.name)}`);
		});
		frm.set_intro(frm.doc.status === "Published"
			? __("Published: parents can see this on the parent portal.")
			: __("Draft: add comments, then publish from the CBC Progress Report list (Publish for a Term)."),
		frm.doc.status === "Published" ? "green" : "blue");
	},
});
