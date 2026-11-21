// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Student"] = {
	add_fields: ["status"],
	onload(listview) {
		if (!frappe.model.can_write("Student")) return;
		const picked = () => listview.get_checked_items(true);
		const need = (fn) => () => (picked().length ? fn(picked()) : frappe.msgprint(__("Tick the learners first.")));
		listview.page.add_actions_menu_item(__("Move to Stream"), need((names) =>
			school_erp.move_class_dialog(names, {}, () => listview.refresh())), false);
		listview.page.add_actions_menu_item(__("Mark as Graduated"), need((names) =>
			school_erp.graduate_dialog(names, "", () => listview.refresh())), false);
	},
	get_indicator(doc) {
		const colour = { Active: "green", Suspended: "orange", Transferred: "blue", Left: "gray", Graduated: "purple" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
