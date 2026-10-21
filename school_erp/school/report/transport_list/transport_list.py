# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range


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
	return columns, rows
