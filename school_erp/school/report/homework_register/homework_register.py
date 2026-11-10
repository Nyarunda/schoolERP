# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col, date_range


@licensing.licensed("Homework")
def execute(filters=None):
	"""Homework set in a period: who set what for which stream, and how much of it was handed in."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = ["h.set_on between %(fd)s and %(td)s", "h.status != 'Draft'"], {"fd": fd, "td": td}
	for key in ("stream", "subject", "teacher", "school_class"):
		if f.get(key):
			cond.append(f"h.{key} = %({key})s")
			args[key] = f.get(key)
	rows = frappe.db.sql(f"""
		select h.name, h.title, h.set_on, h.due_date, h.stream, h.subject, h.teacher, h.status,
			(select count(*) from `tabHomework Submission` s where s.parent = h.name and s.parenttype = 'Homework') learners,
			h.done_count, h.pending_count, h.completion
		from `tabHomework` h where {" and ".join(cond)} order by h.set_on desc, h.stream""", args, as_dict=True)
	columns = [col("name", "Homework", "Link", 120, "Homework"), col("title", "Title", "Data", 200),
			   col("set_on", "Set On", "Date", 95), col("due_date", "Due", "Date", 95), col("stream", "Stream", "Link", 120, "Stream"),
			   col("subject", "Subject", "Link", 120, "Subject"), col("teacher", "Teacher", "Link", 130, "Teacher"),
			   col("learners", "Learners", "Int", 80), col("done_count", "Handed In", "Int", 90),
			   col("pending_count", "Pending", "Int", 80), col("completion", "Completion", "Percent", 100)]
	by_subject = {}
	for r in rows:
		by_subject[r.subject] = by_subject.get(r.subject, 0) + 1
	chart = bar_chart(list(by_subject), list(by_subject.values())) if rows else None
	tracked = [r for r in rows if r.learners]
	avg = round(sum(r.completion or 0 for r in tracked) / len(tracked), 1) if tracked else 0
	summary = [card("Homework set", len(rows), indicator="Blue"), card("Streams", len({r.stream for r in rows})),
			   card("Average completion", avg, "Percent", indicator="Green" if avg >= 80 else "Orange")]
	return columns, rows, None, chart, summary
