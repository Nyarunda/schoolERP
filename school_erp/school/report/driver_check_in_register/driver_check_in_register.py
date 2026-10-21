# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range


def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	from frappe.utils import get_time

	deadline = get_time(frappe.db.get_single_value("School Settings", "driver_checkin_deadline") or "06:30:00")
	cond, args = "", {"fd": fd, "td": td}
	if f.driver:
		cond = " and driver = %(drv)s"; args["drv"] = f.driver
	rows = frappe.db.sql(f"""
		select log_date, trip, driver_name, vehicle, route, check_in_time, fit_to_drive, has_issues, issues,
			odometer_start, odometer_end, distance_km, name, docstatus
		from `tabDriver Daily Log` where log_date between %(fd)s and %(td)s and docstatus < 2 {cond}
		order by log_date desc, check_in_time""", args, as_dict=True)
	for r in rows:
		r.late = int(r.trip == "Morning Pickup" and r.check_in_time is not None and r.check_in_time.time() > deadline)
		r.state = "Submitted" if r.docstatus == 1 else "Draft"
	if f.date_for_missing:
		from school_erp.api.transport_ops import missing_checkins

		for m in missing_checkins(getdate(f.date_for_missing)):
			rows.insert(0, frappe._dict(log_date=getdate(f.date_for_missing), trip="Morning Pickup", driver_name=m["driver_name"],
										route=m["route"], state="NOT CHECKED IN"))
	columns = [
		col("log_date", "Date", "Date", 95), col("trip", "Trip", "Data", 120), col("driver_name", "Driver", "Data", 150),
		col("vehicle", "Vehicle", "Link", 110, "School Vehicle"), col("route", "Route", "Link", 120, "Transport Route"),
		col("check_in_time", "Checked In", "Datetime", 150), col("late", "Late", "Check", 60), col("state", "Status", "Data", 120),
		col("has_issues", "Issues", "Check", 70), col("issues", "Notes", "Data", 200), col("distance_km", "Km", "Float", 70),
		col("name", "Log", "Link", 140, "Driver Daily Log"),
	]
	return columns, rows
