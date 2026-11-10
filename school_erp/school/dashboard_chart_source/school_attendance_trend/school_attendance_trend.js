frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["School Attendance Trend"] = {
	method: "school_erp.school.dashboard_chart_source.school_attendance_trend.school_attendance_trend.get",
	filters: [
		{ fieldname: "show", label: __("Show"), fieldtype: "Select", options: "Attendance %\nAbsent", default: "Attendance %" },
		{ fieldname: "school_class", label: __("Class"), fieldtype: "Link", options: "School Class" },
		{ fieldname: "days", label: __("School days"), fieldtype: "Int", default: 20 },
	],
};
