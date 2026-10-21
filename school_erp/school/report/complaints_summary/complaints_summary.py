# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range


def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	rows = frappe.db.sql("""
		select category, count(*) total, sum(status='Open') open_count, sum(status='In Progress') in_progress,
			sum(status in ('Resolved','Closed')) resolved, round(avg(nullif(days_to_resolve, 0)), 1) avg_days,
			sum(source='Web Form') via_web
		from `tabComplaint` where date(creation) between %s and %s
		group by category order by total desc""", (fd, td), as_dict=True)
	columns = [col("category", "Category", "Data", 160), col("total", "Received", "Int", 90), col("open_count", "Open", "Int", 80),
			   col("in_progress", "In Progress", "Int", 100), col("resolved", "Resolved", "Int", 90),
			   col("avg_days", "Avg Days to Resolve", "Float", 150), col("via_web", "Via Web Form", "Int", 110)]
	chart = {"data": {"labels": [r.category for r in rows], "datasets": [{"name": _("Complaints"), "values": [r.total for r in rows]}]},
			 "type": "pie"} if rows else None
	return columns, rows, None, chart
