# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range


def execute(filters=None):
	f = frappe._dict(filters or {})
	status = f.status or "Active"
	rows = frappe.db.sql("""
		select s.school_class, s.stream,
			sum(s.gender='Female') girls, sum(s.gender='Male') boys, count(*) total,
			sum(s.boarding_type='Boarder') boarders, sum(s.boarding_type='Day') day_scholars,
			sum(ifnull(s.transport_route,'')!='') on_transport, sum(s.takes_lunch=1) lunch
		from `tabStudent` s left join `tabSchool Class` c on c.name = s.school_class
		where s.status = %s
		group by s.school_class, s.stream order by c.level, s.stream""", status, as_dict=True)
	columns = [
		col("school_class", "Class", "Link", 110, "School Class"), col("stream", "Stream", "Link", 140, "Stream"),
		col("girls", "Girls", "Int", 80), col("boys", "Boys", "Int", 80), col("total", "Total", "Int", 80),
		col("boarders", "Boarders", "Int", 90), col("day_scholars", "Day", "Int", 80),
		col("on_transport", "Transport", "Int", 90), col("lunch", "Lunch", "Int", 80),
	]
	total = sum(r.total for r in rows)
	summary = [{"label": _("Students"), "value": total, "datatype": "Int", "indicator": "Blue"},
			   {"label": _("Girls"), "value": sum(r.girls or 0 for r in rows), "datatype": "Int"},
			   {"label": _("Boys"), "value": sum(r.boys or 0 for r in rows), "datatype": "Int"}]
	return columns, rows, None, None, summary
