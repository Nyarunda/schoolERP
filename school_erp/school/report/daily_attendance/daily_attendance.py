# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp.api.attendance import day_summary
from school_erp.api.report_utils import bar_chart, col


def execute(filters=None):
	f = frappe._dict(filters or {})
	frappe.has_permission("Class Attendance", "read", throw=True)
	s = day_summary(f.date)
	teachers = dict(frappe.get_all("Teacher", fields=["name", "teacher_name"], as_list=True))
	data = []
	for r in s["streams"]:
		if f.school_class and r["school_class"] != f.school_class:
			continue
		data.append({**r, "class_teacher_name": teachers.get(r["class_teacher"], ""), "taken": 1 if r["taken"] else 0})
	data.sort(key=lambda r: (r["taken"], r["stream"]))  # registers still missing first
	columns = [
		col("stream", "Stream", "Link", 120, "Stream"), col("school_class", "Class", "Link", 100, "School Class"),
		col("class_teacher_name", "Class Teacher", "Data", 170), col("taken", "Register", "Data", 110),
		col("students", "Students", "Int", 90), col("present", "Present", "Int", 80), col("late", "Late", "Int", 70),
		col("absent", "Absent", "Int", 80), col("percent", "Attendance %", "Percent", 110),
		col("register", "Register No.", "Link", 140, "Class Attendance"),
	]
	summary = [
		{"label": _("Registers taken"), "value": f"{s['taken']} / {s['total']}", "datatype": "Data",
		 "indicator": "Green" if s["taken"] == s["total"] else "Orange"},
		{"label": _("Attendance"), "value": s["percent"] or 0, "datatype": "Percent"},
		{"label": _("Absent"), "value": s["absent"], "datatype": "Int", "indicator": "Red" if s["absent"] else "Green"},
	]
	taken = [r for r in data if r["taken"]]
	chart = bar_chart([r["stream"] for r in taken], [(_("Attendance %"), [r["percent"] or 0 for r in taken])]) if taken else None
	if chart:
		chart["fieldtype"] = "Percent"
	return columns, data, None, chart, summary
