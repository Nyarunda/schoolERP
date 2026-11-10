// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Homework"] = {
	add_fields: ["status", "due_date"],
	get_indicator(doc) {
		if (doc.status === "Draft") return [__("Draft"), "orange", "status,=,Draft"];
		if (doc.status === "Closed") return [__("Closed"), "gray", "status,=,Closed"];
		return doc.due_date < frappe.datetime.get_today() ? [__("Past Due"), "blue", "status,=,Published"] : [__("Published"), "green", "status,=,Published"];
	},
};
