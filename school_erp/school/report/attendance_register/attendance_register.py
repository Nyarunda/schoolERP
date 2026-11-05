# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from school_erp.api.report_utils import col
from school_erp.logic.attendance import rate


def execute(filters=None):
	f = frappe._dict(filters or {})
	frappe.has_permission("Class Attendance", "read", throw=True)
	from_date, to_date = getdate(f.from_date), getdate(f.to_date)
	cond, args = "", {"from": from_date, "to": to_date}
	if f.stream:
		cond += " and ca.stream = %(stream)s"
		args["stream"] = f.stream
	if f.school_class:
		cond += " and ca.school_class = %(cls)s"
		args["cls"] = f.school_class
	rows = frappe.db.sql(
		f"""select s.student, st.student_name, ca.stream,
			count(*) marked, sum(s.status='Present') present, sum(s.status='Absent') absent,
			sum(s.status='Late') late, sum(s.status='Excused') excused
		from `tabClass Attendance Student` s
		join `tabClass Attendance` ca on ca.name = s.parent
		left join `tabStudent` st on st.name = s.student
		where ca.attendance_date between %(from)s and %(to)s {cond}
		group by s.student, st.student_name, ca.stream
		order by ca.stream, st.student_name""", args, as_dict=True)
	data = []
	for r in rows:
		r["percent"] = rate(int(r.present) + int(r.late), int(r.marked))
		if f.below and (r["percent"] is None or r["percent"] >= flt(f.below)):
			continue
		data.append(r)
	columns = [
		col("student", "Student", "Link", 120, "Student"), col("student_name", "Name", "Data", 190),
		col("stream", "Stream", "Link", 110, "Stream"), col("marked", "Days marked", "Int", 100),
		col("present", "Present", "Int", 80), col("late", "Late", "Int", 70), col("absent", "Absent", "Int", 80),
		col("excused", "Excused", "Int", 80), col("percent", "Attendance %", "Percent", 110),
	]
	marked = sum(int(r.marked) for r in data)
	attended = sum(int(r.present) + int(r.late) for r in data)
	summary = [
		{"label": _("Students"), "value": len(data), "datatype": "Int"},
		{"label": _("Overall attendance"), "value": rate(attended, marked) or 0, "datatype": "Percent",
		 "indicator": "Green" if (rate(attended, marked) or 0) >= 90 else "Orange"},
		{"label": _("Absences"), "value": sum(int(r.absent) for r in data), "datatype": "Int", "indicator": "Red"},
		{"label": _("Below 90%"), "value": sum(1 for r in data if (r["percent"] or 0) < 90), "datatype": "Int"},
	]
	return columns, data, None, None, summary
