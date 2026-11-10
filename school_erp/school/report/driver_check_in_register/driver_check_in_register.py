# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card
from school_erp import licensing


@licensing.licensed("Driver Daily Log")
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
	logs = [r for r in rows if r.get("name")]
	morning = [r for r in logs if r.trip == "Morning Pickup"]
	missing = [r for r in rows if r.get("state") == "NOT CHECKED IN"]
	summary = [
		card("Check-ins", len(logs)), card("Late morning check-ins", sum(r.late for r in morning), indicator="Orange" if any(r.late for r in morning) else "Green"),
		card("With vehicle issues", sum(1 for r in logs if r.has_issues), indicator="Red" if any(r.has_issues for r in logs) else "Green"),
		card("Not fit to drive", sum(1 for r in logs if r.fit_to_drive == 0), indicator="Red" if any(r.fit_to_drive == 0 for r in logs) else "Green"),
		card("Km driven", round(sum(flt(r.distance_km) for r in logs)), "Float"),
	]
	if f.date_for_missing:
		summary.insert(0, card("Not checked in", len(missing), indicator="Red" if missing else "Green"))
	days = {}
	for r in morning:
		d = days.setdefault(r.log_date, [0, 0])
		d[1 if r.late else 0] += 1
	labels = sorted(days)
	chart = bar_chart([frappe.format(d, "Date") for d in labels], [(_("On time"), [days[d][0] for d in labels]), (_("Late"), [days[d][1] for d in labels])], stacked=True) if labels else None
	return columns, rows, None, chart, summary
