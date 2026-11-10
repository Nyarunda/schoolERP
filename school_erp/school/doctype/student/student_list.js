// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Student"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { Active: "green", Suspended: "orange", Transferred: "blue", Left: "gray", Graduated: "purple" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
