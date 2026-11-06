# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card, top
from school_erp import licensing


@licensing.licensed("Complaint")
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
	# one stacked bar per category: how many are still open vs dealt with
	chart = bar_chart([r.category for r in rows], [(_("Open"), [r.open_count for r in rows]), (_("In progress"), [r.in_progress for r in rows]),
												   (_("Resolved"), [r.resolved for r in rows])], stacked=True) if rows else None
	total = sum(r.total for r in rows)
	open_n = sum((r.open_count or 0) + (r.in_progress or 0) for r in rows)
	days = [flt(r.avg_days) for r in rows if r.avg_days]
	summary = [card("Received", total), card("Still open", open_n, indicator="Orange" if open_n else "Green"),
			   card("Resolved", sum(r.resolved or 0 for r in rows), indicator="Green"),
			   card("Avg days to resolve", round(sum(days) / len(days), 1) if days else 0, "Float"),
			   card("Via web form", sum(r.via_web or 0 for r in rows))]
	return columns, rows, None, chart, summary
