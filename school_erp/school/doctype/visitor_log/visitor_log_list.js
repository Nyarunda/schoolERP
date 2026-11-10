// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Visitor Log"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return doc.status === "On premises" ? [__("On premises"), "orange", "status,=,On premises"] : [__("Signed out"), "green", "status,=,Signed out"];
	},
};
