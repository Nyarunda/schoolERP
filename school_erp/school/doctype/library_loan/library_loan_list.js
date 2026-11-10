// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Library Loan"] = {
	add_fields: ["status", "due_date"],
	get_indicator(doc) {
		if (doc.status === "On Loan" && doc.due_date < frappe.datetime.get_today()) return [__("Overdue"), "red", "status,=,On Loan"];
		return [__(doc.status), { "On Loan": "blue", Returned: "green", Lost: "gray" }[doc.status], `status,=,${doc.status}`];
	},
};
