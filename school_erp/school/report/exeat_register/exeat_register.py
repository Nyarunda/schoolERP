# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col, date_range
from school_erp.logic.boarding import is_overdue


@licensing.licensed("Exeat")
def execute(filters=None):
	"""Who left, who collected them, when they came back, and who is still out."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = ["date(e.departure) between %(fd)s and %(td)s"], {"fd": fd, "td": td}
	if f.status in ("Requested", "Approved", "Out", "Returned", "Rejected", "Cancelled"):
		cond.append("e.status = %(status)s")
		args["status"] = f.status
	if f.dormitory:
		cond.append("e.dormitory = %(dorm)s")
		args["dorm"] = f.dormitory
	if f.out_now:
		cond = ["e.status = 'Out'"]
	rows = frappe.db.sql(f"""select e.name, e.student, e.student_name, e.school_class, e.dormitory, e.exeat_type, e.status,
			e.departure, e.expected_return, e.actual_departure, e.actual_return, e.minutes_late, e.picked_by_name,
			e.picked_by_relation, e.picked_by_phone
		from `tabExeat` e where {" and ".join(cond)} order by e.departure desc""", args, as_dict=True)
	now = now_datetime()
	for r in rows:
		r["overdue"] = 1 if r.status == "Out" and is_overdue(r.expected_return, now, 0) else 0
	columns = [col("name", "Exeat", "Link", 120, "Exeat"), col("student_name", "Learner", "Data", 170),
			   col("school_class", "Class", "Link", 90, "School Class"), col("dormitory", "Dormitory", "Link", 120, "Dormitory"),
			   col("exeat_type", "Type", "Data", 100), col("status", "Status", "Data", 90),
			   col("departure", "Leaving", "Datetime", 145), col("expected_return", "Back By", "Datetime", 145),
			   col("actual_return", "Returned", "Datetime", 145), col("minutes_late", "Minutes Late", "Int", 100),
			   col("overdue", "Overdue", "Check", 80), col("picked_by_name", "Collected By", "Data", 140),
			   col("picked_by_relation", "Relationship", "Data", 100), col("picked_by_phone", "Phone", "Data", 115)]
	by_type = {}
	for r in rows:
		by_type[r.exeat_type] = by_type.get(r.exeat_type, 0) + 1
	chart = bar_chart(list(by_type), list(by_type.values())) if rows else None
	out = sum(1 for r in rows if r.status == "Out")
	overdue = sum(r["overdue"] for r in rows)
	late = sum(1 for r in rows if (r.minutes_late or 0) > 0)
	summary = [card("Exeats", len(rows), indicator="Blue"), card("Out now", out, indicator="Orange" if out else "Green"),
			   card("Overdue", overdue, indicator="Red" if overdue else "Green"), card("Came back late", late)]
	return columns, rows, None, chart, summary
