# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range
from school_erp import licensing


@licensing.licensed("Driver Daily Log")
def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	rows = frappe.db.sql("""
		select vehicle, count(*) trips, sum(distance_km) km, sum(fuel_added_litres) litres, sum(fuel_cost) fuel_cost,
			sum(has_issues) issue_days
		from `tabDriver Daily Log` where docstatus = 1 and log_date between %s and %s
		group by vehicle order by vehicle""", (fd, td), as_dict=True)
	for r in rows:
		r.km_per_litre = round(flt(r.km) / flt(r.litres), 2) if flt(r.litres) else None
		r.cost_per_km = round(flt(r.fuel_cost) / flt(r.km), 2) if flt(r.km) else None
	columns = [col("vehicle", "Vehicle", "Link", 120, "School Vehicle"), col("trips", "Trips", "Int", 70), col("km", "Km", "Float", 90),
			   col("litres", "Fuel (L)", "Float", 90), col("fuel_cost", "Fuel Cost", "Currency", 120),
			   col("km_per_litre", "Km / L", "Float", 80), col("cost_per_km", "Cost / Km", "Currency", 100),
			   col("issue_days", "Check-ins with Issues", "Int", 160)]
	return columns, rows
