frappe.query_reports["Exam Subject Analysis"] = {
	filters: [{ fieldname: "exam", label: __("Exam"), fieldtype: "Link", options: "Exam" }],
	onload(report) {
		if (report.get_filter_value("exam")) return;
		frappe.db.get_list("Exam", { fields: ["name"], order_by: "creation desc", limit: 1 })
			.then((rows) => rows.length && report.set_filter_value("exam", rows[0].name));
	},
};
