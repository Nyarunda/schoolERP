# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card, top
from school_erp import licensing


@licensing.licensed("Timetable")
def execute(filters=None):
	f = frappe._dict(filters or {})
	term = f.school_term
	if not term:
		from school_erp.school.doctype.school_term.school_term import get_current_term

		t = get_current_term()
		term = t.name if t else None
	if not term:
		return [], []
	rows = frappe.db.sql("""
		select ts.teacher, tc.teacher_name, count(*) lessons, count(distinct t.stream) streams, count(distinct ts.subject) subjects,
			group_concat(distinct ts.subject order by ts.subject separator ', ') subject_list
		from `tabTimetable Slot` ts join `tabTimetable` t on t.name = ts.parent
		left join `tabTeacher` tc on tc.name = ts.teacher
		where t.school_term = %s and ifnull(ts.teacher, '') != ''
		group by ts.teacher, tc.teacher_name order by lessons desc""", term, as_dict=True)
	columns = [col("teacher", "Teacher", "Link", 110, "Teacher"), col("teacher_name", "Name", "Data", 170),
			   col("lessons", "Lessons / Week", "Int", 120), col("streams", "Classes", "Int", 80), col("subjects", "Subjects", "Int", 80),
			   col("subject_list", "Teaches", "Data", 300)]
	for r in rows:
		r["label"] = r.teacher_name or r.teacher
	labels, values = top(rows, "label", "lessons", n=20)
	chart = bar_chart(labels, [(_("Lessons / week"), values)]) if rows else None
	lessons = [r.lessons for r in rows]
	summary = [card("Teachers", len(rows)), card("Lessons / week", sum(lessons)),
			   card("Average per teacher", round(sum(lessons) / len(lessons), 1) if lessons else 0, "Float", indicator="Blue"),
			   card("Busiest", max(lessons) if lessons else 0, indicator="Orange")]
	return columns, rows, None, chart, summary
