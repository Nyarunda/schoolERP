// Copyright (c) 2026, School ERP and contributors

frappe.listview_settings["Admission Application"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { "Received": "blue", "Under Review": "orange", "Interview Scheduled": "purple", "Offered": "cyan",
			"Accepted": "light-blue", "Admitted": "green", "Rejected": "red", "Withdrawn": "gray" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
