# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range
from school_erp import licensing


@licensing.licensed("Duty Report")
def execute(filters=None):
	"""Each school day in the range with who was on duty and whether they reported."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	from frappe.utils import add_days, date_diff

	from school_erp.api.staff import on_duty_today

	reports = {}
	for r in frappe.get_all("Duty Report", filters={"report_date": ("between", [fd, td]), "docstatus": ("<", 2)},
							fields=["name", "report_date", "staff_member", "staff_name", "overall_rating", "incidents", "docstatus",
									"students_late", "lessons_ok", "meals_ok"]):
		reports[(str(r.report_date), r.staff_member)] = r
	data, seen = [], set()
	d = getdate(fd)
	for _i in range(date_diff(td, fd) + 1):
		if d.weekday() < 5:
			for staff in on_duty_today(d):
				r = reports.get((str(d), staff))
				seen.add((str(d), staff))
				data.append(_row(d, staff, r))
		d = add_days(d, 1)
	for key, r in reports.items():  # reports filed by staff not on the roster
		if key not in seen:
			data.append(_row(getdate(r.report_date), r.staff_member, r))
	data.sort(key=lambda x: (x["date"], x["staff_name"] or ""))
	columns = [
		col("date", "Date", "Date", 100), col("staff_name", "Teacher on Duty", "Data", 170), col("status", "Report", "Data", 110),
		col("overall_rating", "Day", "Data", 80), col("students_late", "Late", "Int", 70), col("issues", "Flags", "Data", 260),
		col("name", "Duty Report", "Link", 140, "Duty Report"),
	]
	missing = sum(1 for r in data if r["status"] == "Missing")
	summary = [{"label": _("Reports submitted"), "value": sum(1 for r in data if r["status"] == "Submitted"), "datatype": "Int", "indicator": "Green"},
			   {"label": _("Missing"), "value": missing, "datatype": "Int", "indicator": "Red" if missing else "Green"}]
	return columns, data, None, None, summary


def _row(d, staff, r):
	name = frappe.db.get_value("Staff Member", staff, "full_name")
	if not r:
		return {"date": d, "staff_name": name, "status": "Missing"}
	flags = []
	if r.incidents:
		flags.append("incidents")
	if not r.lessons_ok:
		flags.append("missed lessons")
	if not r.meals_ok:
		flags.append("meals")
	return {"date": d, "staff_name": name, "status": "Submitted" if r.docstatus == 1 else "Draft", "overall_rating": r.overall_rating,
			"students_late": r.students_late, "issues": ", ".join(flags), "name": r.name}
