# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card, top
from school_erp import licensing


@licensing.licensed("Fee Payment")
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
	spent = {} if licensing._hidden("School Expense") else by_month("""select date_format(posting_date,'%%Y-%%m'), sum(amount)
		from `tabSchool Expense` where docstatus=1 and status='Approved' and posting_date between %s and %s group by 1""", (fd, td))
	months = sorted(set(billed) | set(collected) | set(spent))
	data = [{"month": m, "billed": billed.get(m, 0), "collected": collected.get(m, 0), "expenses": spent.get(m, 0),
			 "net": collected.get(m, 0) - spent.get(m, 0)} for m in months]
	columns = [col("month", "Month", "Data", 100), col("billed", "Fees Billed", "Currency", 140), col("collected", "Fees Collected", "Currency", 140),
			   col("expenses", "Expenses", "Currency", 140), col("net", "Collected - Expenses", "Currency", 170)]
	chart = {"data": {"labels": months, "datasets": [
		{"name": _("Collected"), "values": [d["collected"] for d in data]},
		{"name": _("Expenses"), "values": [d["expenses"] for d in data]}]}, "type": "bar", "fieldtype": "Currency"} if months else None
	tb, tc, te = (sum(d[k] for d in data) for k in ("billed", "collected", "expenses"))
	summary = [card("Fees billed", tb, "Currency"), card("Fees collected", tc, "Currency", indicator="Green"),
			   card("Collection rate", round(tc / tb * 100, 1) if tb else 0, "Percent"),
			   card("Expenses", te, "Currency", indicator="Orange"),
			   card("Collected - expenses", tc - te, "Currency", indicator="Green" if tc >= te else "Red")]
	return columns, data, None, chart, summary
