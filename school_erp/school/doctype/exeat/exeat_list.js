// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Exeat"] = {
	add_fields: ["status", "expected_return"],
	get_indicator(doc) {
		if (doc.status === "Out" && doc.expected_return < frappe.datetime.now_datetime()) return [__("Overdue"), "red", "status,=,Out"];
		const colour = { Requested: "orange", Approved: "blue", Out: "purple", Returned: "green", Rejected: "red", Cancelled: "gray" }[doc.status];
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
