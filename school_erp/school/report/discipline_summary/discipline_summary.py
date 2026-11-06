# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card, top
from school_erp import licensing


@licensing.licensed("Discipline Incident")
def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	group = f.group_by or "Class"
	key = {"Class": "school_class", "Category": "category", "Student": "student"}[group]
	cond, args = "", {"fd": fd, "td": td}
	if f.school_class:
		cond = " and school_class = %(cls)s"; args["cls"] = f.school_class
	rows = frappe.db.sql(f"""
		select {key} as grp, max(student_name) student_name, count(*) total,
			sum(severity='Minor') minor, sum(severity='Major') major, sum(severity='Critical') critical,
			sum(status!='Resolved') open_cases, sum(action_taken='Suspension') suspensions
		from `tabDiscipline Incident` where incident_date between %(fd)s and %(td)s {cond}
		group by {key} order by total desc""", args, as_dict=True)
	label = {"Class": "Class", "Category": "Category", "Student": "Student"}[group]
	columns = [col("grp", label, "Link" if group != "Category" else "Data", 160, {"Class": "School Class", "Student": "Student"}.get(group))]
	if group == "Student":
		columns.append(col("student_name", "Name", "Data", 170))
	columns += [col("total", "Incidents", "Int", 90), col("minor", "Minor", "Int", 80), col("major", "Major", "Int", 80),
				col("critical", "Critical", "Int", 80), col("open_cases", "Open", "Int", 80), col("suspensions", "Suspensions", "Int", 100)]
	shown = rows[:15]
	chart = bar_chart([str(r.grp) for r in shown], [(_("Minor"), [r.minor for r in shown]), (_("Major"), [r.major for r in shown]),
													(_("Critical"), [r.critical for r in shown])], stacked=True) if rows else None
	open_n = sum(r.open_cases or 0 for r in rows)
	summary = [card("Incidents", sum(r.total for r in rows)), card("Still open", open_n, indicator="Orange" if open_n else "Green"),
			   card("Critical", sum(r.critical or 0 for r in rows), indicator="Red" if any(r.critical for r in rows) else "Green"),
			   card("Suspensions", sum(r.suspensions or 0 for r in rows))]
	return columns, rows, None, chart, summary
