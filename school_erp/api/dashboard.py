"""Data for the Management Dashboard and the Staff Room. Every section is skipped when its module isn't licensed."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	cint,
	flt,
	formatdate,
	get_first_day,
	get_time,
	getdate,
	now_datetime,
	nowdate,
	strip_html,
)

from school_erp import licensing
from school_erp.api.notify import staff_for_user

MANAGEMENT_ROLES = {"System Manager", "School Admin", "Head Teacher", "Bursar"}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _current_term(term=None):
	if term:
		return frappe.get_doc("School Term", term)
	from school_erp.school.doctype.school_term.school_term import get_current_term

	return get_current_term()


def _attention(label, count, route, tone="warning", amount=None, hint=None):
	return {"label": label, "count": cint(count), "route": route, "tone": tone, "amount": amount, "hint": hint}


# ============================================================================ management
@frappe.whitelist()
def management(term=None):
	if not set(frappe.get_roles()) & MANAGEMENT_ROLES:
		frappe.throw(_("The Management Dashboard is for school leadership"), frappe.PermissionError)
	state = licensing.get_state()
	mods = set(state["modules"])
	t = _current_term(term)
	today = getdate(nowdate())
	settings = frappe.get_cached_doc("School Settings")
	out = {
		"school": settings.school_name or "School",
		"currency": settings.currency,
		"today": formatdate(today, "EEEE d MMMM yyyy"),
		"term": t.name if t else None,
		"terms": frappe.get_all("School Term", order_by="start_date desc", pluck="name", limit=9),
		"modules": sorted(mods),
		"license": {"status": state["status"], "message": state["message"]},
		"attention": [],
	}
	out["students"] = _students(t)
	out["attendance"] = _attendance_today(today)
	if "fees" in mods:
		out["fees"] = _fees(t, today)
	if "staff" in mods:
		out["staff"] = _staff_today(today)
	if "transport_ops" in mods:
		out["transport"] = _transport_today(today)
	if "welfare" in mods:
		out["welfare"] = _welfare(t, today)
	if "expenses" in mods:
		out["expenses"] = _expenses(today)
	if "fees" in mods or "expenses" in mods:
		out["cashflow"] = _cashflow(today)
	out["attention"] = _management_attention(mods, today)
	out["notices"] = notices_for(None, limit=6, management=True)
	return out


def _students(t):
	rows = frappe.db.sql(
		"""select count(*) total, sum(gender='Female') girls, sum(gender='Male') boys,
			sum(boarding_type='Boarder') boarders
		from `tabStudent` where status='Active'""", as_dict=True)[0]
	new = 0
	if t:
		new = frappe.db.count("Student", {"status": "Active", "admission_date": ("between", [t.start_date, t.end_date])})
	by_class = frappe.db.sql(
		"""select s.school_class label, count(*) value from `tabStudent` s
		left join `tabSchool Class` c on c.name = s.school_class
		where s.status='Active' group by s.school_class order by c.level""", as_dict=True)
	return {"total": cint(rows.total), "girls": cint(rows.girls), "boys": cint(rows.boys),
			"boarders": cint(rows.boarders), "new_this_term": new, "by_class": by_class}


def _fees(t, today):
	billed = outstanding = 0
	if t:
		r = frappe.db.sql(
			"""select coalesce(sum(grand_total),0), coalesce(sum(outstanding_amount),0) from `tabSales Invoice`
			where docstatus=1 and is_return=0 and school_term=%s""", t.name)[0]
		billed, outstanding = flt(r[0]), flt(r[1])
	collected_term = billed - outstanding
	all_outstanding = flt(frappe.db.sql(
		"""select coalesce(sum(outstanding_amount),0) from `tabSales Invoice`
		where docstatus=1 and is_return=0 and ifnull(student,'')!='' and outstanding_amount>0""")[0][0])
	today_r = frappe.db.sql(
		"select coalesce(sum(amount),0), count(*) from `tabFee Payment` where docstatus=1 and posting_date=%s", today)[0]
	week_start = add_days(today, -today.weekday())
	week = flt(frappe.db.sql(
		"select coalesce(sum(amount),0) from `tabFee Payment` where docstatus=1 and posting_date between %s and %s",
		(week_start, today))[0][0])

	# daily collections, last 4 weeks + today (29 points keeps the axis labels evenly spaced)
	start = add_days(today, -28)
	daily = {str(r[0]): flt(r[1]) for r in frappe.db.sql(
		"""select posting_date, sum(amount) from `tabFee Payment` where docstatus=1 and posting_date between %s and %s
		group by posting_date""", (start, today))}
	labels, values = [], []
	for i in range(29):
		d = add_days(start, i)
		labels.append(formatdate(d, "d MMM"))
		values.append(daily.get(str(d), 0))

	by_class = []
	if t:
		by_class = frappe.db.sql(
			"""select s.school_class label, sum(si.outstanding_amount) value, count(distinct si.student) students
			from `tabSales Invoice` si join `tabStudent` s on s.name = si.student
			left join `tabSchool Class` c on c.name = s.school_class
			where si.docstatus=1 and si.is_return=0 and si.school_term=%s and si.outstanding_amount>0
			group by s.school_class order by c.level""", t.name, as_dict=True)
	defaulters = 0
	if t:
		defaulters = cint(frappe.db.sql(
			"""select count(distinct student) from `tabSales Invoice`
			where docstatus=1 and is_return=0 and school_term=%s and outstanding_amount>0""", t.name)[0][0])

	paybill = None
	if licensing.is_enabled("mpesa"):
		p = frappe.db.sql(
			"""select coalesce(sum(case when status='Posted' and date(trans_time)=%s then amount end),0),
				sum(status in ('Unmatched','Failed')), coalesce(sum(case when status in ('Unmatched','Failed') then amount end),0)
			from `tabM-Pesa Transaction`""", today)[0]
		paybill = {"today": flt(p[0]), "unmatched": cint(p[1]), "unmatched_amount": flt(p[2])}
	return {
		"billed": billed, "collected": collected_term, "outstanding": outstanding,
		"rate": round(collected_term / billed * 100, 1) if billed else None,
		"all_outstanding": all_outstanding, "today": flt(today_r[0]), "today_count": cint(today_r[1]), "week": week,
		"daily": {"labels": labels, "values": values}, "by_class": by_class, "defaulters": defaulters, "paybill": paybill,
	}


def _staff_today(today):
	total = frappe.db.count("Staff Member", {"status": ("!=", "Left")})
	away = frappe.db.sql(
		"""select la.staff_name, la.leave_type, la.to_date, la.reliever_name, la.name
		from `tabLeave Application` la
		where la.docstatus=1 and la.status='Approved' and %s between la.from_date and la.to_date
		order by la.staff_name""", today, as_dict=True)
	for a in away:
		a["back"] = formatdate(add_days(a.to_date, 1), "EEE d MMM")
	from school_erp.api.staff import on_duty_today

	duty = []
	for s in on_duty_today(today):
		rep = frappe.db.get_value("Duty Report", {"staff_member": s, "report_date": today, "docstatus": ("<", 2)},
								  ["name", "docstatus", "overall_rating"], as_dict=True)
		duty.append({"staff": frappe.db.get_value("Staff Member", s, "full_name"),
					 "report": rep.name if rep else None,
					 "status": ("Submitted" if rep.docstatus == 1 else "Draft") if rep else "Not yet",
					 "rating": rep.overall_rating if rep else None})
	return {"total": total, "on_leave": away, "present": total - len(away), "duty": duty}


def _transport_today(today):
	routes = frappe.get_all("Transport Route", filters={"is_active": 1, "driver": ("is", "set")}, fields=["name", "driver"])
	logs = {r.driver: r for r in frappe.get_all(
		"Driver Daily Log", filters={"log_date": today, "trip": "Morning Pickup", "docstatus": 1},
		fields=["driver", "driver_name", "vehicle", "check_in_time", "has_issues", "name"])}
	rows = []
	for r in routes:
		log = logs.get(r.driver)
		rows.append({
			"route": r.name,
			"driver": frappe.db.get_value("Staff Member", r.driver, "full_name"),
			"checked_in": log.check_in_time.strftime("%H:%M") if log and log.check_in_time else None,
			"vehicle": log.vehicle if log else None,
			"issues": cint(log.has_issues) if log else 0,
			"log": log.name if log else None,
		})
	return {"routes": len(routes), "checked_in": sum(1 for r in rows if r["checked_in"]),
			"issues": sum(r["issues"] for r in rows), "rows": rows}


def _welfare(t, today):
	open_c = frappe.db.sql(
		"""select count(*), sum(priority in ('High','Urgent')) from `tabComplaint` where status in ('Open','In Progress')""")[0]
	start = t.start_date if t else add_days(today, -90)
	cats = frappe.db.sql(
		"""select category label, count(*) value from `tabDiscipline Incident`
		where incident_date >= %s group by category order by value desc""", start, as_dict=True)
	week = frappe.db.count("Discipline Incident", {"incident_date": (">=", add_days(today, -today.weekday()))})
	serious_open = frappe.db.count("Discipline Incident", {"status": ("!=", "Resolved"), "severity": ("in", ["Major", "Critical"])})
	return {"open_complaints": cint(open_c[0]), "urgent_complaints": cint(open_c[1]), "incidents_week": week,
			"serious_open": serious_open, "by_category": cats}


def _expenses(today):
	r = frappe.db.sql(
		"""select sum(status='Pending Approval'), sum(status='Pending Final Approval'),
			coalesce(sum(case when status in ('Pending Approval','Pending Final Approval') then amount end),0),
			coalesce(sum(case when status='Approved' and posting_date >= %s then amount end),0)
		from `tabSchool Expense` where docstatus < 2""", get_first_day(today))[0]
	return {"pending_first": cint(r[0]), "pending_final": cint(r[1]), "pending_amount": flt(r[2]), "month_spent": flt(r[3])}


def _cashflow(today):
	"""Fees collected and school expenses, per month, last 6 months (two series, one axis: both are money)."""
	start = get_first_day(add_months(today, -5))
	months = [formatdate(add_months(start, i), "MMM") for i in range(6)]
	keys = [add_months(start, i).strftime("%Y-%m") for i in range(6)]
	col = {r[0]: flt(r[1]) for r in frappe.db.sql(
		"""select date_format(posting_date,'%%Y-%%m'), sum(amount) from `tabFee Payment`
		where docstatus=1 and posting_date >= %s group by 1""", start)}
	exp = {}
	if licensing.is_enabled("expenses"):
		exp = {r[0]: flt(r[1]) for r in frappe.db.sql(
			"""select date_format(posting_date,'%%Y-%%m'), sum(amount) from `tabSchool Expense`
			where docstatus=1 and status='Approved' and posting_date >= %s group by 1""", start)}
	return {"labels": months, "collected": [col.get(k, 0) for k in keys], "expenses": [exp.get(k, 0) for k in keys]}


def _attendance_today(today):
	from school_erp.api.attendance import day_summary, is_school_day

	s = day_summary(today)
	if not s["taken"] and not is_school_day(today):
		return None  # weekend or holiday: no tile
	return {"percent": s["percent"], "absent": s["absent"], "taken": s["taken"], "total": s["total"],
			"missing": [r["stream"] for r in s["streams"] if not r["taken"]]}


def _management_attention(mods, today):
	items = []
	from school_erp.api.attendance import is_school_day

	if is_school_day(today) and now_datetime().hour >= 9:  # give class teachers the first hour
		att = _attendance_today(today) or {}
		if att.get("missing"):
			items.append(_attention(_("Class registers not taken today"), len(att["missing"]), ["query-report", "Daily Attendance"],
									hint=", ".join(att["missing"][:6])))
	if "exams" in mods:
		n = frappe.db.count("Exam Mark Sheet", {"docstatus": 0, "approval_status": "Pending Approval"})
		if n:
			items.append(_attention(_("Mark sheets waiting for approval"), n, ["List", "Exam Mark Sheet", {"approval_status": "Pending Approval"}]))
	if "staff" in mods:
		n = frappe.db.count("Leave Application", {"docstatus": 0, "status": "Pending Approval"})
		if n:
			items.append(_attention(_("Leave requests to approve"), n, ["List", "Leave Application", {"status": "Pending Approval"}]))
	if "expenses" in mods:
		n1 = frappe.db.count("School Expense", {"docstatus": 0, "status": "Pending Approval"})
		n2 = frappe.db.count("School Expense", {"docstatus": 0, "status": "Pending Final Approval"})
		if n1:
			items.append(_attention(_("Expenses awaiting first approval"), n1, ["List", "School Expense", {"status": "Pending Approval"}]))
		if n2:
			items.append(_attention(_("Expenses awaiting final approval"), n2, ["List", "School Expense", {"status": "Pending Final Approval"}]))
	if "mpesa" in mods:
		n = frappe.db.count("M-Pesa Transaction", {"status": ("in", ["Unmatched", "Failed", "Needs Review"])})
		if n:
			items.append(_attention(_("M-Pesa payments for the bursar to check"), n,
									["List", "M-Pesa Transaction", {"status": ["in", ["Unmatched", "Failed", "Needs Review"]]}], "serious"))
	if "welfare" in mods:
		n = frappe.db.count("Complaint", {"status": ("in", ["Open", "In Progress"]), "priority": ("in", ["High", "Urgent"])})
		if n:
			items.append(_attention(_("Urgent / high-priority complaints open"), n, ["List", "Complaint", {"status": "Open"}], "critical"))
		old = frappe.db.count("Complaint", {"status": "Open", "creation": ("<", add_days(today, -3))})
		if old:
			items.append(_attention(_("Complaints open more than 3 days"), old, ["List", "Complaint", {"status": "Open"}]))
	if "transport_ops" in mods:
		deadline = get_time(frappe.db.get_single_value("School Settings", "driver_checkin_deadline") or "06:30:00")
		if now_datetime().time() > deadline and today.weekday() < 6:
			from school_erp.api.transport_ops import missing_checkins

			miss = missing_checkins(today)
			if miss:
				items.append(_attention(_("Drivers not checked in today"), len(miss), ["query-report", "Driver Check-in Register"], "critical",
										hint=", ".join(m["driver_name"] for m in miss[:4])))
		issues = frappe.db.count("Driver Daily Log", {"log_date": today, "docstatus": 1, "has_issues": 1})
		if issues:
			items.append(_attention(_("Vehicles with check issues today"), issues, ["List", "Driver Daily Log", {"log_date": str(today), "has_issues": 1}], "serious"))
	if "staff" in mods:
		due = get_time(frappe.db.get_single_value("School Settings", "duty_report_due_time") or "17:00:00")
		if now_datetime().time() > due and today.weekday() < 5:
			from school_erp.api.staff import on_duty_today

			miss = [s for s in on_duty_today(today)
					if not frappe.db.exists("Duty Report", {"staff_member": s, "report_date": today, "docstatus": 1})]
			if miss:
				items.append(_attention(_("Duty report not submitted today"), len(miss), ["query-report", "Duty Reports Register"]))
	return items


# ============================================================================ notices
def notices_for(user=None, limit=8, management=False):
	"""Live notices for this user's audience (management sees all, with reach)."""
	user = user or frappe.session.user
	today = nowdate()
	audiences = None
	if not management:
		staff = staff_for_user(user)
		stype = frappe.db.get_value("Staff Member", staff, "staff_type") if staff else None
		audiences = ["All Staff"]
		if stype == "Teaching":
			audiences.append("Teaching Staff")
		elif stype:
			audiences.append("Non-Teaching Staff")
		if stype == "Driver":
			audiences.append("Drivers")
		if set(frappe.get_roles(user)) & {"Head Teacher", "School Admin", "Bursar"}:
			audiences.append("Management")
	filters = {"publish_date": ("<=", today), "expiry_date": (">=", today)}
	if audiences:
		filters["audience"] = ("in", audiences)
	rows = frappe.get_all("School Notice", filters=filters,
						  fields=["name", "title", "message", "priority", "audience", "publish_date", "pinned", "posted_by",
								  "audience_count", "acknowledged_count"],
						  order_by="pinned desc, publish_date desc, creation desc", limit=limit)
	acked = set(frappe.get_all("Notice Acknowledgement", filters={"user": user, "parent": ("in", [r.name for r in rows] or [""])},
							   pluck="parent"))
	for r in rows:
		r["text"] = strip_html(r.message or "")[:400]
		r.pop("message", None)
		r["date"] = formatdate(r.publish_date, "d MMM")
		r["by"] = frappe.utils.get_fullname(r.posted_by) if r.posted_by else ""
		r["acknowledged"] = r.name in acked
	return rows


# ============================================================================ staff room
@frappe.whitelist()
def staff_room():
	user = frappe.session.user
	staff = staff_for_user(user)
	mods = set(licensing.get_state()["modules"])
	today = getdate(nowdate())
	t = _current_term()
	sm = frappe.db.get_value("Staff Member", staff, ["full_name", "staff_type", "designation", "teacher"], as_dict=True) if staff else None
	name = (sm.full_name if sm else frappe.utils.get_fullname(user)) or user
	hour = now_datetime().hour
	out = {
		"greeting": (_("Good morning") if hour < 12 else _("Good afternoon") if hour < 17 else _("Good evening")) + f", {name.split(' ')[0]}",
		"today": formatdate(today, "EEEE d MMMM yyyy"),
		"term": t.name if t else None,
		"staff": staff,
		"staff_type": sm.staff_type if sm else None,
		"designation": sm.designation if sm else None,
		"modules": sorted(mods),
		"is_management": bool(set(frappe.get_roles(user)) & MANAGEMENT_ROLES),
	}
	teacher = (sm.teacher if sm else None) or frappe.db.get_value("Teacher", {"user": user})
	if "timetable" in mods and teacher and t:
		out["lessons"] = _lessons_today(teacher, t.name, today)
		out["week_lessons"] = frappe.db.sql(
			"""select count(*) from `tabTimetable Slot` ts join `tabTimetable` tt on tt.name = ts.parent
			where ts.teacher=%s and tt.school_term=%s""", (teacher, t.name))[0][0]
	if teacher:
		out["my_classes"] = _my_classes(teacher, t, mods)
	if frappe.has_permission("Class Attendance", "create"):
		from school_erp.api.attendance import is_school_day

		out["can_take_register"] = True
		out["school_day"] = is_school_day(today)
		taken = set(frappe.get_all("Class Attendance", filters={"attendance_date": today}, pluck="stream"))
		for c in out.get("my_classes") or []:
			c["register_taken"] = c["stream"] in taken
	if "exams" in mods and set(frappe.get_roles(user)) & {"Head of Department", "Head Teacher", "School Admin"}:
		from school_erp.api.exams import approval_queue_names

		out["marks_to_approve"] = len(approval_queue_names(user=user))
	if "staff" in mods and staff:
		out["duty"] = _my_duty(staff, today)
		from school_erp.api.staff import leave_balances

		out["leave"] = [b for b in leave_balances(staff) if b["entitled"] and _leave_type_applies(b["leave_type"], staff)]
		out["my_leave"] = frappe.get_all(
			"Leave Application", filters={"staff_member": staff, "docstatus": ("<", 2), "to_date": (">=", today),
										  "status": ("in", ["Pending Approval", "Approved"])},
			fields=["name", "leave_type", "from_date", "to_date", "status"], order_by="from_date", limit=3)
		for l in out["my_leave"]:
			l["period"] = f"{formatdate(l.from_date, 'd MMM')} - {formatdate(l.to_date, 'd MMM')}"
		out["relieving"] = frappe.db.sql(
			"""select staff_name, leave_type, from_date, to_date, name from `tabLeave Application`
			where reliever=%s and docstatus=1 and status='Approved' and to_date >= %s order by from_date limit 3""",
			(staff, today), as_dict=True)
		for r in out["relieving"]:
			r["period"] = f"{formatdate(r.from_date, 'd MMM')} - {formatdate(r.to_date, 'd MMM')}"
			r["now"] = getdate(r.from_date) <= today
		out["away_today"] = frappe.db.sql(
			"""select staff_name, reliever_name from `tabLeave Application`
			where docstatus=1 and status='Approved' and %s between from_date and to_date order by staff_name""",
			today, as_dict=True)
	if out["staff_type"] == "Driver" and "transport_ops" in mods:
		out["checkin"] = frappe.db.get_value("Driver Daily Log", {"driver": staff, "log_date": today, "trip": "Morning Pickup",
																   "docstatus": ("<", 2)}, ["name", "docstatus", "has_issues"], as_dict=True)
	out["notices"] = notices_for(user)
	out["actions"] = _actions(out, mods)
	return out


def _leave_type_applies(leave_type, staff) -> bool:
	"""Hide e.g. Maternity Leave from male staff and teaching-only types from support staff."""
	lt = frappe.get_cached_doc("Leave Type", leave_type)
	sm = frappe.db.get_value("Staff Member", staff, ["gender", "staff_type"], as_dict=True)
	if (lt.gender or "All") != "All" and sm.gender and sm.gender != lt.gender:
		return False
	if lt.applies_to == "Teaching" and sm.staff_type != "Teaching":
		return False
	if lt.applies_to == "Non-Teaching" and sm.staff_type == "Teaching":
		return False
	return True


def _lessons_today(teacher, term, today):
	day = DAYS[today.weekday()]
	rows = frappe.db.sql(
		"""select p.period_name, p.start_time, p.end_time, p.sequence, ts.subject, tt.stream, ts.room
		from `tabTimetable Slot` ts join `tabTimetable` tt on tt.name = ts.parent
		join `tabPeriod` p on p.name = ts.period
		where ts.teacher=%s and tt.school_term=%s and ts.day=%s order by p.sequence""",
		(teacher, term, day), as_dict=True)
	now = now_datetime().time()
	found_next = False
	for r in rows:
		start, end = get_time(r.start_time), get_time(r.end_time)
		r["time"] = f"{start:%H:%M}-{end:%H:%M}"
		r["state"] = "done" if end <= now else "now" if start <= now < end else "next" if not found_next else "later"
		if r["state"] == "next":
			found_next = True
		r.pop("start_time"), r.pop("end_time")
	return rows


def _my_classes(teacher, t, mods):
	streams = frappe.get_all("Stream", filters={"class_teacher": teacher, "is_active": 1}, pluck="name")
	out = []
	for s in streams:
		c = frappe.db.sql("""select count(*), sum(gender='Female'), sum(gender='Male') from `tabStudent`
			where stream=%s and status='Active'""", s)[0]
		row = {"stream": s, "students": cint(c[0]), "girls": cint(c[1]), "boys": cint(c[2])}
		if "welfare" in mods:
			row["incidents"] = frappe.db.count("Discipline Incident", {"stream": s, "incident_date": (">=", t.start_date if t else add_days(nowdate(), -90))})
		out.append(row)
	return out


def _my_duty(staff, today):
	roster = frappe.db.sql(
		"""select r.name, r.from_date, r.to_date, m.duty_role from `tabDuty Roster Member` m
		join `tabDuty Roster` r on r.name = m.parent
		where m.staff_member=%s and r.to_date >= %s order by r.from_date limit 1""", (staff, today), as_dict=True)
	if not roster:
		return None
	r = roster[0]
	report = frappe.db.get_value("Duty Report", {"staff_member": staff, "report_date": today, "docstatus": ("<", 2)},
								 ["name", "docstatus"], as_dict=True)
	return {"role": r.duty_role, "period": f"{formatdate(r.from_date, 'd MMM')} - {formatdate(r.to_date, 'd MMM')}",
			"on_duty_now": getdate(r.from_date) <= today <= getdate(r.to_date),
			"report": report.name if report else None, "submitted": bool(report and report.docstatus == 1)}


def _actions(out, mods):
	a = []
	if out.get("can_take_register") and (out.get("my_classes") or out.get("staff_type") == "Teaching"):
		mine = (out.get("my_classes") or [{}])[0].get("stream")
		a.append({"label": _("Take register"), "icon": "check", "route": ["class-register", {"stream": mine} if mine else {}]})
	if "staff" in mods and out.get("staff"):
		a.append({"label": _("Apply for leave"), "icon": "calendar", "route": ["Form", "Leave Application", "new"]})
		if (out.get("duty") or {}).get("on_duty_now"):
			a.append({"label": _("Duty report"), "icon": "clipboard", "route": ["Form", "Duty Report", out["duty"]["report"] or "new"]})
	if "welfare" in mods and out.get("staff_type") == "Teaching":
		a.append({"label": _("Record discipline incident"), "icon": "alert", "route": ["Form", "Discipline Incident", "new"]})
	if out.get("staff_type") == "Driver" and "transport_ops" in mods:
		a.append({"label": _("Morning check-in"), "icon": "bus", "route": ["Form", "Driver Daily Log", (out.get("checkin") or {}).get("name") or "new"]})
	if "expenses" in mods:
		a.append({"label": _("Raise an expense"), "icon": "receipt", "route": ["Form", "School Expense", "new"]})
	if "timetable" in mods:
		a.append({"label": _("Timetables"), "icon": "grid", "route": ["List", "Timetable"]})
	return a
