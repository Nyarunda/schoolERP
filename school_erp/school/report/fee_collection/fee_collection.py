# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range
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
	rows = frappe.db.sql(f"""
		select fp.posting_date, fp.name, fp.student, fp.student_name, fp.school_class, fp.mode_of_payment,
			fp.reference_no, fp.amount, fp.owner
		from `tabFee Payment` fp where fp.docstatus = 1 and fp.posting_date between %(fd)s and %(td)s {cond}
		order by fp.posting_date, fp.creation""", args, as_dict=True)
	columns = [
		col("posting_date", "Date", "Date", 100), col("name", "Receipt", "Link", 140, "Fee Payment"),
		col("student", "Student ID", "Link", 120, "Student"), col("student_name", "Name", "Data", 180),
		col("school_class", "Class", "Link", 100, "School Class"), col("mode_of_payment", "Mode", "Link", 110, "Mode of Payment"),
		col("reference_no", "Reference", "Data", 120), col("amount", "Amount", "Currency", 120), col("owner", "Received By", "Data", 140),
	]
	by_day = {}
	for r in rows:
		by_day[str(r.posting_date)] = by_day.get(str(r.posting_date), 0) + flt(r.amount)
	chart = {"data": {"labels": list(by_day), "datasets": [{"name": _("Collected"), "values": list(by_day.values())}]},
			 "type": "bar", "fieldtype": "Currency"} if by_day else None
	by_mode = {}
	for r in rows:
		by_mode[r.mode_of_payment] = by_mode.get(r.mode_of_payment, 0) + flt(r.amount)
	summary = [{"label": _("Total collected"), "value": sum(by_mode.values()), "datatype": "Currency", "indicator": "Green"}] + [
		{"label": m, "value": v, "datatype": "Currency"} for m, v in by_mode.items()]
	return columns, rows, None, chart, summary
