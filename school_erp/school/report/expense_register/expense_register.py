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
	if f.expense_category:
		cond += " and expense_category = %(cat)s"; args["cat"] = f.expense_category
	if f.status:
		cond += " and status = %(st)s"; args["st"] = f.status
	rows = frappe.db.sql(f"""
		select posting_date, name, expense_category, payee, description, amount, mode_of_payment, status, requested_by, journal_entry
		from `tabSchool Expense` where posting_date between %(fd)s and %(td)s and docstatus < 2 {cond}
		order by posting_date""", args, as_dict=True)
	columns = [
		col("posting_date", "Date", "Date", 95), col("name", "Expense", "Link", 140, "School Expense"),
		col("expense_category", "Category", "Link", 160, "Expense Category"), col("payee", "Paid To", "Data", 150),
		col("description", "For", "Data", 220), col("amount", "Amount", "Currency", 110), col("mode_of_payment", "Paid From", "Data", 110),
		col("status", "Status", "Data", 140), col("requested_by", "Requested By", "Data", 150), col("journal_entry", "Journal Entry", "Link", 140, "Journal Entry"),
	]
	approved = sum(flt(r.amount) for r in rows if r.status == "Approved")
	pending = sum(flt(r.amount) for r in rows if r.status in ("Pending Approval", "Pending Final Approval"))
	by_cat = {}
	for r in rows:
		if r.status == "Approved":
			by_cat[r.expense_category] = by_cat.get(r.expense_category, 0) + flt(r.amount)
	chart = {"data": {"labels": list(by_cat), "datasets": [{"name": _("Approved"), "values": list(by_cat.values())}]},
			 "type": "donut", "fieldtype": "Currency"} if by_cat else None
	summary = [{"label": _("Approved & posted"), "value": approved, "datatype": "Currency", "indicator": "Green"},
			   {"label": _("Awaiting approval"), "value": pending, "datatype": "Currency", "indicator": "Orange"}]
	return columns, rows, None, chart, summary
