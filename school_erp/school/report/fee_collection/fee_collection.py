# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import bar_chart, card, col, date_range
from school_erp import licensing


@licensing.licensed("Fee Payment")
def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = "", {"fd": fd, "td": td}
	if f.mode_of_payment:
		cond += " and fp.mode_of_payment = %(mop)s"; args["mop"] = f.mode_of_payment
	if f.school_class:
		cond += " and fp.school_class = %(cls)s"; args["cls"] = f.school_class
	if f.student:
		cond += " and fp.student = %(stu)s"; args["stu"] = f.student
	rows = frappe.db.sql(f"""
		select fp.posting_date, fp.name, fp.student, fp.student_name, fp.school_class, fp.mode_of_payment,
			fp.reference_no, fp.amount, fp.owner
		from `tabFee Payment` fp where fp.docstatus = 1 and fp.posting_date between %(fd)s and %(td)s {cond}
		order by fp.posting_date, fp.creation""", args, as_dict=True)
	columns = [
		col("posting_date", "Date", "Date", 110), col("name", "Receipt", "Link", 170, "Fee Payment"),
		col("student", "Student ID", "Link", 120, "Student"), col("student_name", "Name", "Data", 180),
		col("school_class", "Class", "Link", 100, "School Class"), col("mode_of_payment", "Mode", "Link", 110, "Mode of Payment"),
		col("reference_no", "Reference", "Data", 120), col("amount", "Amount", "Currency", 120), col("owner", "Received By", "Data", 140),
	]
	total = sum(flt(r.amount) for r in rows)
	by_mode = {}
	for r in rows:
		by_mode[r.mode_of_payment or _("Not set")] = by_mode.get(r.mode_of_payment or _("Not set"), 0) + flt(r.amount)
	modes = sorted(by_mode.items(), key=lambda kv: -kv[1])
	summary = [
		card("Total collected", total, "Currency", indicator="Green"),
		card("Receipts", len(rows)),
		card("Students who paid", len({r.student for r in rows})),
		card("Average payment", round(total / len(rows)) if rows else 0, "Currency"),
	] + [card(m, v, "Currency") for m, v in modes[:3]]
	return columns, rows, None, _trend(rows, fd, td) if rows else None, summary


def _trend(rows, fd, td):
	"""Collections over the period: by day up to ~6 weeks, by week up to ~6 months, then by month."""
	days = (getdate(td) - getdate(fd)).days
	if days <= 45:
		key, label = (lambda d: d), (lambda d: frappe.format(d, "Date"))
	elif days <= 190:
		key = lambda d: d - timedelta(days=d.weekday())  # Monday of that week
		label = lambda d: _("w/c {0}").format(d.strftime("%d %b"))
	else:
		key, label = (lambda d: d.replace(day=1)), (lambda d: d.strftime("%b %Y"))
	buckets = {}
	for r in rows:
		k = key(getdate(r.posting_date))
		buckets[k] = buckets.get(k, 0) + flt(r.amount)
	ks = sorted(buckets)
	return bar_chart([label(k) for k in ks], [(_("Collected"), [buckets[k] for k in ks])], money=True)
