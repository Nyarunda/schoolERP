"""Attendance over the last school days. Only days with registers are plotted, so weekends and holidays
don't appear as zero attendance (a standard date-based chart fills those gaps with 0)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, getdate, nowdate
from frappe.utils.dashboard import cache_source


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None, timespan=None,
		time_interval=None, heatmap_year=None):
	frappe.has_permission("Class Attendance", "read", throw=True)
	if chart_name:
		chart = frappe.get_doc("Dashboard Chart", chart_name, check_permission="read")
	else:
		chart = frappe._dict(frappe.parse_json(chart))
	filters = frappe.parse_json(filters) or frappe.parse_json(chart.filters_json) or {}
	days = cint(filters.get("days")) or 20
	show = filters.get("show") or "Attendance %"
	cond, args = "", {"to": getdate(nowdate()), "from": add_days(getdate(nowdate()), -days * 3)}
	if filters.get("school_class"):
		cond = " and school_class = %(cls)s"
		args["cls"] = filters["school_class"]
	rows = frappe.db.sql(
		f"""select attendance_date, sum(present + late) attended, sum(absent) absent, sum(total_students) marked
		from `tabClass Attendance` where attendance_date between %(from)s and %(to)s {cond}
		group by attendance_date order by attendance_date""", args, as_dict=True)[-days:]
	if show == "Absent":
		values = [cint(r.absent) for r in rows]
	else:
		values = [round(flt(r.attended) / flt(r.marked) * 100, 1) if flt(r.marked) else 0 for r in rows]
	# bars get narrow with many days: a short day/month label fits under each one without being cut off
	fmt = "d/M" if show == "Absent" or len(rows) > 12 else "EEE d MMM"
	return {"labels": [formatdate(r.attendance_date, fmt) for r in rows],
			"datasets": [{"name": _(show), "values": values}]}
