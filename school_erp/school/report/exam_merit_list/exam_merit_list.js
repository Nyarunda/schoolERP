frappe.query_reports["Exam Merit List"] = {
	filters: [
		{ fieldname: "exam", label: __("Exam"), fieldtype: "Link", options: "Exam" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "stream", label: __("Stream"), fieldtype: "Link", options: "Stream" },
		{ fieldname: "rank_by", label: __("Rank by"), fieldtype: "Select", options: "Class\nStream", default: "Class" },
	],
	onload(report) {
		if (report.get_filter_value("exam")) return;
		frappe.db.get_list("Exam", { fields: ["name"], order_by: "creation desc", limit: 1 })
			.then((rows) => rows.length && report.set_filter_value("exam", rows[0].name));
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "change" && data && data.change) {
			value = `<span style="color:var(--${data.change > 0 ? "green" : "red"}-600)">${data.change > 0 ? "▲ +" : "▼ "}${Math.abs(data.change)}</span>`;
		}
		return value;
	},
};
