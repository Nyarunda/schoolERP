# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range


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
	colors = {"Posted": "Green", "Unmatched": "Orange", "Failed": "Red"}
	summary = [{"label": s, "value": v, "datatype": "Currency", "indicator": colors.get(s, "Grey")} for s, v in totals.items()]
	return columns, rows, None, None, summary
