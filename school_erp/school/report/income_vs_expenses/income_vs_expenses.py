# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range


def execute(filters=None):
	"""Per month: fees billed, fees collected, school expenses approved, and the cash difference."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	def by_month(sql, args):
		return {r[0]: flt(r[1]) for r in frappe.db.sql(sql, args)}
	billed = by_month("""select date_format(posting_date,'%%Y-%%m'), sum(grand_total) from `tabSales Invoice`
		where docstatus=1 and is_return=0 and ifnull(student,'')!='' and posting_date between %s and %s group by 1""", (fd, td))
	collected = by_month("""select date_format(posting_date,'%%Y-%%m'), sum(amount) from `tabFee Payment`
		where docstatus=1 and posting_date between %s and %s group by 1""", (fd, td))
	spent = by_month("""select date_format(posting_date,'%%Y-%%m'), sum(amount) from `tabSchool Expense`
		where docstatus=1 and status='Approved' and posting_date between %s and %s group by 1""", (fd, td))
	months = sorted(set(billed) | set(collected) | set(spent))
	data = [{"month": m, "billed": billed.get(m, 0), "collected": collected.get(m, 0), "expenses": spent.get(m, 0),
			 "net": collected.get(m, 0) - spent.get(m, 0)} for m in months]
	columns = [col("month", "Month", "Data", 100), col("billed", "Fees Billed", "Currency", 140), col("collected", "Fees Collected", "Currency", 140),
			   col("expenses", "Expenses", "Currency", 140), col("net", "Collected - Expenses", "Currency", 170)]
	chart = {"data": {"labels": months, "datasets": [
		{"name": _("Collected"), "values": [d["collected"] for d in data]},
		{"name": _("Expenses"), "values": [d["expenses"] for d in data]}]}, "type": "bar", "fieldtype": "Currency"} if months else None
	return columns, data, None, chart
