# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.api.report_utils import col


def execute(filters=None):
	"""Mean score per subject per stream for an exam, with grade spread."""
	f = frappe._dict(filters or {})
	if not f.exam:
		return [col("info", "Pick an exam", "Data", 300)], []
	sheets = frappe.get_all("Exam Mark Sheet", filters={"exam": f.exam, "docstatus": 1},
							fields=["name", "stream", "subject", "teacher", "max_marks", "average", "highest", "lowest", "entered"])
	teacher_names = dict(frappe.get_all("Teacher", fields=["name", "teacher_name"], as_list=True))
	data = []
	for sh in sorted(sheets, key=lambda s: (s.subject, s.stream)):
		mx = flt(sh.max_marks) or 100
		grades = {}
		for g in frappe.get_all("Exam Mark", filters={"parent": sh.name}, pluck="grade"):
			if g:
				grades[g] = grades.get(g, 0) + 1
		data.append({"subject": sh.subject, "stream": sh.stream, "teacher": teacher_names.get(sh.teacher, ""),
					 "students": sh.entered, "mean_pct": round(flt(sh.average) / mx * 100, 1),
					 "highest": sh.highest, "lowest": sh.lowest,
					 "grades": "  ".join(f"{k}:{v}" for k, v in sorted(grades.items()))})
	columns = [col("subject", "Subject", "Link", 140, "Subject"), col("stream", "Stream", "Link", 130, "Stream"),
			   col("teacher", "Teacher", "Data", 140), col("students", "Students", "Int", 80), col("mean_pct", "Mean %", "Float", 80),
			   col("highest", "Highest", "Float", 80), col("lowest", "Lowest", "Float", 80), col("grades", "Grade spread", "Data", 260)]
	by_subject = {}
	for d in data:
		by_subject.setdefault(d["subject"], []).append(d["mean_pct"])
	chart = {"data": {"labels": list(by_subject), "datasets": [{"name": _("Mean %"), "values": [round(sum(v) / len(v), 1) for v in by_subject.values()]}]},
			 "type": "bar"} if by_subject else None
	return columns, data, None, chart
