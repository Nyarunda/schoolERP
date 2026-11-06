# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card
from school_erp import licensing


@licensing.licensed("Leave Application")
def execute(filters=None):
	f = frappe._dict(filters or {})
	day = f.date or nowdate()
	rows = frappe.db.sql("""
		select la.staff_member, la.staff_name, sm.staff_type, sm.designation, la.leave_type, la.from_date, la.to_date,
			la.total_days, la.reliever, la.reliever_name, rs.phone reliever_phone, la.name
		from `tabLeave Application` la
		join `tabStaff Member` sm on sm.name = la.staff_member
		left join `tabStaff Member` rs on rs.name = la.reliever
		where la.docstatus = 1 and la.status = 'Approved' and %s between la.from_date and la.to_date
		order by sm.staff_type, la.staff_name""", day, as_dict=True)
	columns = [
		col("staff_name", "Away", "Data", 170), col("staff_type", "Type", "Data", 100), col("designation", "Designation", "Data", 120),
		col("leave_type", "Leave", "Link", 130, "Leave Type"), col("from_date", "From", "Date", 95), col("to_date", "Back After", "Date", 95),
		col("reliever_name", "Reliever", "Data", 160), col("reliever_phone", "Reliever Phone", "Data", 120),
		col("name", "Application", "Link", 140, "Leave Application"),
	]
	by_type = {}
	for r in rows:
		by_type[r.leave_type] = by_type.get(r.leave_type, 0) + 1
	summary = [card("Away", len(rows), indicator="Orange" if rows else "Green"),
			   card("Without a reliever", sum(1 for r in rows if not r.reliever), indicator="Red" if any(not r.reliever for r in rows) else "Green"),
			   card("Teaching staff away", sum(1 for r in rows if r.staff_type == "Teaching"))]
	chart = bar_chart(list(by_type), list(by_type.values())) if len(by_type) > 1 else None
	return columns, rows, None, chart, summary
