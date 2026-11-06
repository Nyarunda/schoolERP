# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card
from school_erp import licensing


@licensing.licensed("Transport Route")
def execute(filters=None):
	"""Students per route with pick-up point and parent phone, for drivers; or the lunch list."""
	f = frappe._dict(filters or {})
	if f.list_type == "Lunch":
		cond, args = "s.takes_lunch = 1", {}
	else:
		cond, args = "ifnull(s.transport_route, '') != ''", {}
		if f.route:
			cond += " and s.transport_route = %(route)s"; args["route"] = f.route
	if f.school_class:
		cond += " and s.school_class = %(cls)s"; args["cls"] = f.school_class
	rows = frappe.db.sql(f"""
		select s.transport_route, s.pickup_point, s.name student, s.student_name, s.school_class, s.stream,
			s.primary_guardian, s.primary_phone
		from `tabStudent` s where s.status = 'Active' and {cond}
		order by s.transport_route, s.pickup_point, s.student_name""", args, as_dict=True)
	columns = []
	if f.list_type != "Lunch":
		columns += [col("transport_route", "Route", "Link", 120, "Transport Route"), col("pickup_point", "Pick-up Point", "Data", 150)]
	columns += [col("student", "Student ID", "Link", 120, "Student"), col("student_name", "Name", "Data", 180),
				col("stream", "Class", "Link", 130, "Stream"), col("primary_guardian", "Parent", "Data", 150),
				col("primary_phone", "Parent Phone", "Data", 120)]
	if f.list_type == "Lunch":
		by = {}
		for r in rows:
			by[r.stream or _("Not set")] = by.get(r.stream or _("Not set"), 0) + 1
		return columns, rows, None, bar_chart(list(by), [(_("Students"), list(by.values()))]) if by else None, [card("Students taking lunch", len(rows), indicator="Blue")]
	by = {}
	for r in rows:
		by[r.transport_route] = by.get(r.transport_route, 0) + 1
	summary = [card("Students on transport", len(rows), indicator="Blue"), card("Routes", len(by)),
			   card("Pick-up points", len({(r.transport_route, r.pickup_point) for r in rows if r.pickup_point})),
			   card("No parent phone", sum(1 for r in rows if not r.primary_phone), indicator="Red" if any(not r.primary_phone for r in rows) else "Green")]
	return columns, rows, None, bar_chart(list(by), [(_("Students"), list(by.values()))]) if by else None, summary
