# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card, top
from school_erp import licensing


@licensing.licensed("Fee Payment")
def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = "", {"fd": fd, "td": td}
	if f.status:
		cond = " and status = %(st)s"; args["st"] = f.status
	rows = frappe.db.sql(f"""
		select trans_time, name, amount, bill_ref_number, payer_name, status, student, student_name, fee_payment, error
		from `tabM-Pesa Transaction` where date(trans_time) between %(fd)s and %(td)s {cond}
		order by trans_time""", args, as_dict=True)
	columns = [
		col("trans_time", "Paid On", "Datetime", 150), col("name", "M-Pesa Code", "Link", 120, "M-Pesa Transaction"),
		col("amount", "Amount", "Currency", 110), col("bill_ref_number", "Account Entered", "Data", 130),
		col("payer_name", "Payer", "Data", 150), col("status", "Status", "Data", 100),
		col("student", "Student", "Link", 120, "Student"), col("student_name", "Name", "Data", 160),
		col("fee_payment", "Receipt", "Link", 140, "Fee Payment"), col("error", "Note", "Data", 220),
	]
	totals = {}
	for r in rows:
		totals[r.status] = totals.get(r.status, 0) + flt(r.amount)
	colors = {"Posted": "Green", "Unmatched": "Orange", "Failed": "Red", "Needs Review": "Red"}
	summary = [card("Payments", len(rows))] + [card(s, v, "Currency", indicator=colors.get(s, "Grey")) for s, v in totals.items()]
	# amount per day: posted to a student vs still to check
	days = {}
	for r in rows:
		d = days.setdefault(r.trans_time.date() if r.trans_time else None, [0, 0])
		d[0 if r.status == "Posted" else 1] += flt(r.amount)
	labels = sorted(d for d in days if d)
	chart = bar_chart([frappe.format(d, "Date") for d in labels], [(_("Posted"), [days[d][0] for d in labels]),
																 (_("To check"), [days[d][1] for d in labels])], money=True, stacked=True) if labels else None
	return columns, rows, None, chart, summary
