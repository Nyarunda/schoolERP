// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Timetable", {
	setup(frm) {
		frm.set_query("teacher", "slots", () => ({ filters: { is_active: 1 } }));
		frm.set_query("period", "slots", () => ({ filters: { is_break: 0 } }));
	},
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print Timetable"), () => frm.print_doc());
		}
	},
});
