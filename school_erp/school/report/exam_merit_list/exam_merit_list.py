# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.api.report_utils import col


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not f.exam:
		return [col("info", "Pick an exam", "Data", 300)], []
	exam = frappe.get_cached_doc("Exam", f.exam)
	subjects = [s.subject for s in exam.subjects] or sorted({r.subject for r in frappe.get_all(
		"Report Card Subject", filters={"parent": ("in", frappe.get_all("Report Card", {"exam": f.exam}, pluck="name") or [""])}, fields=["subject"])})
	cond = {"exam": f.exam}
	if f.school_class:
		cond["school_class"] = f.school_class
	if f.stream:
		cond["stream"] = f.stream
	order = "stream asc, stream_position asc" if f.rank_by == "Stream" else "class_position asc"
	cards = frappe.get_all("Report Card", filters=cond, order_by=order,
						   fields=["name", "student", "student_name", "stream", "class_position", "stream_position", "total_marks",
								   "mean_percent", "mean_grade", "mean_points", "previous_mean"])
	marks = {}
	for r in frappe.get_all("Report Card Subject", filters={"parent": ("in", [c.name for c in cards] or [""])},
							fields=["parent", "subject", "marks", "grade"]):
		marks[(r.parent, r.subject)] = r
	columns = [col("pos", "Pos", "Int", 60), col("student", "Student ID", "Link", 120, "Student"), col("student_name", "Name", "Data", 170),
			   col("stream", "Stream", "Link", 120, "Stream")]
	for s in subjects:
		columns.append(col(f"s_{s}", s[:12], "Data", 85))
	columns += [col("total_marks", "Total", "Float", 80), col("mean_percent", "Mean %", "Float", 80), col("mean_grade", "Grade", "Data", 65),
				col("change", "+/- vs last", "Float", 90), col("name", "Report Card", "Link", 140, "Report Card")]
	data = []
	for c in cards:
		row = {"pos": c.stream_position if f.rank_by == "Stream" else c.class_position, **c,
			   "change": round(flt(c.mean_percent) - flt(c.previous_mean), 1) if c.previous_mean else None}
		for s in subjects:
			m = marks.get((c.name, s))
			row[f"s_{s}"] = (f"{flt(m.marks):g} {m.grade}" if m.marks is not None and m.grade != "ABS" else "ABS") if m else ""
		data.append(row)
	means = [flt(c.mean_percent) for c in cards if c.mean_percent]
	summary = [{"label": _("Students"), "value": len(cards), "datatype": "Int"},
			   {"label": _("Average mean"), "value": round(sum(means) / len(means), 1) if means else 0, "datatype": "Float", "indicator": "Blue"}]
	return columns, data, None, None, summary
