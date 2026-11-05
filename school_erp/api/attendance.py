"""Daily class attendance: the phone-friendly Class Register, absence SMS to parents, and summaries for dashboards,
reports and the parent portal."""

import json

import frappe
from frappe import _
from frappe.utils import cint, formatdate, getdate, nowdate

from school_erp import licensing
from school_erp.logic.attendance import ATTENDING, STATUSES, rate


def stream_students(stream):
	return frappe.get_all("Student", filters={"stream": stream, "status": "Active"},
						  fields=["name", "student_name", "first_name", "gender", "photo"], order_by="student_name")


def _my_teacher(user=None):
	return frappe.db.get_value("Teacher", {"user": user or frappe.session.user})


@frappe.whitelist()
def my_streams():
	"""The streams this user is class teacher of first, then every other active stream."""
	frappe.has_permission("Class Attendance", "read", throw=True)
	teacher = _my_teacher()
	mine = frappe.get_all("Stream", filters={"class_teacher": teacher, "is_active": 1}, pluck="name", order_by="name") if teacher else []
	others = [s for s in frappe.get_all("Stream", filters={"is_active": 1}, pluck="name", order_by="name") if s not in mine]
	return {"mine": mine, "others": others}


@frappe.whitelist()
def register(stream, date=None):
	"""What the Class Register page shows for one stream and day."""
	frappe.has_permission("Class Attendance", "read", throw=True)
	day = getdate(date or nowdate())
	name = frappe.db.get_value("Class Attendance", {"stream": stream, "attendance_date": day})
	saved = {}
	meta = {}
	if name:
		doc = frappe.get_doc("Class Attendance", name)
		saved = {r.student: {"status": r.status, "note": r.note} for r in doc.students}
		meta = {"name": name, "taken_by": frappe.utils.get_fullname(doc.marked_by),
				"taken_at": frappe.format(doc.modified, "Datetime"), "percent": doc.attendance_percent}
	students = []
	for s in stream_students(stream):
		row = saved.pop(s.name, None) or {"status": "Present", "note": ""}
		students.append({"student": s.name, "name": s.student_name, "first_name": s.first_name,
						 "photo": s.photo, "status": row["status"], "note": row["note"] or ""})
	# students who left the stream after the register was taken stay on that day's register
	for st, row in saved.items():
		students.append({"student": st, "name": frappe.db.get_value("Student", st, "student_name"), "first_name": "",
						 "photo": None, "status": row["status"], "note": row["note"] or "", "moved": 1})
	can_edit = frappe.has_permission("Class Attendance", "write" if name else "create")
	if can_edit:
		try:
			frappe.get_doc({"doctype": "Class Attendance", "attendance_date": day}).check_edit_window(day, getdate(nowdate()))
		except frappe.PermissionError as e:
			frappe.clear_messages()
			can_edit, meta["locked"] = False, str(e)
	return {"stream": stream, "date": str(day), "date_label": formatdate(day, "EEEE d MMM yyyy"),
			"students": students, "saved": meta, "can_edit": bool(can_edit), "future": day > getdate(nowdate())}


@frappe.whitelist(methods=["POST"])
def save_register(stream, date, rows):
	"""Create or update the day's register. rows: [{student, status, note}]"""
	rows = json.loads(rows) if isinstance(rows, str) else rows
	day = getdate(date)
	name = frappe.db.get_value("Class Attendance", {"stream": stream, "attendance_date": day})
	doc = frappe.get_doc("Class Attendance", name) if name else frappe.new_doc("Class Attendance")
	doc.update({"stream": stream, "attendance_date": day})
	# update rows in place so what is already recorded on them (e.g. that the parent was texted) is kept
	existing = {r.student: r for r in doc.students}
	keep = []
	for r in rows:
		row = existing.get(r["student"]) or frappe._dict(doctype="Class Attendance Student", student=r["student"])
		row.status = r.get("status") or "Present"
		row.note = (r.get("note") or "").strip()[:140]
		keep.append(row)
	doc.set("students", keep)
	doc.save()  # permissions and the edit window are checked by the DocType
	return {"name": doc.name, "present": doc.present, "absent": doc.absent, "late": doc.late, "excused": doc.excused,
			"percent": doc.attendance_percent, "notified": len(doc.flags.newly_absent or []) if _sms_on() and day == getdate(nowdate()) else 0}


# ----------------------------------------------------------------------------- absence SMS
def _sms_on():
	return bool(frappe.db.get_single_value("School Settings", "attendance_sms_absent")) and licensing.is_enabled("messaging")


def queue_absence_sms(doc):
	"""Only for today's register: an SMS about a day long gone would alarm a parent for nothing."""
	if not _sms_on() or getdate(doc.attendance_date) != getdate(nowdate()):
		return
	frappe.enqueue("school_erp.api.attendance.send_absence_sms", queue="short", name=doc.name,
				   students=list(doc.flags.newly_absent), enqueue_after_commit=True, now=bool(frappe.flags.in_test))


def send_absence_sms(name, students):
	from school_erp.api.messaging import sms_student

	template = frappe.db.get_single_value("School Settings", "attendance_absent_sms")
	if not template:
		return
	doc = frappe.get_doc("Class Attendance", name)
	day = formatdate(doc.attendance_date, "d MMM yyyy")
	for row in doc.students:
		if row.student not in students or row.status != "Absent" or row.parent_notified:
			continue
		try:
			r = sms_student(frappe.get_doc("Student", row.student), template, {"date": day})
			if r.get("sent"):
				frappe.db.set_value("Class Attendance Student", row.name, "parent_notified", 1, update_modified=False)
		except Exception:
			frappe.log_error(title=f"Absence SMS failed: {row.student}")


# ----------------------------------------------------------------------------- summaries
def day_summary(day=None):
	"""Every active stream with whether today's register is in, for dashboards."""
	day = getdate(day or nowdate())
	taken = {r.stream: r for r in frappe.get_all(
		"Class Attendance", filters={"attendance_date": day},
		fields=["name", "stream", "present", "absent", "late", "excused", "total_students", "attendance_percent", "marked_by"])}
	streams = frappe.get_all("Stream", filters={"is_active": 1}, fields=["name", "school_class", "class_teacher"], order_by="name")
	counts = {s: n for s, n in frappe.db.sql(
		"select stream, count(*) from `tabStudent` where status='Active' and ifnull(stream,'')!='' group by stream")}
	rows, attending, marked = [], 0, 0
	for s in streams:
		if not counts.get(s.name):
			continue  # an empty stream has no register to take
		r = taken.get(s.name)
		if r:
			attending += cint(r.present) + cint(r.late)
			marked += cint(r.total_students)
		rows.append({"stream": s.name, "school_class": s.school_class, "class_teacher": s.class_teacher,
					 "students": counts.get(s.name, 0), "taken": bool(r), "register": r.name if r else None,
					 "present": cint(r.present) if r else None, "absent": cint(r.absent) if r else None,
					 "late": cint(r.late) if r else None, "percent": r.attendance_percent if r else None})
	return {"date": str(day), "streams": rows, "taken": sum(1 for r in rows if r["taken"]), "total": len(rows),
			"absent": sum(r["absent"] or 0 for r in rows), "percent": rate(attending, marked)}


def is_school_day(day=None) -> bool:
	"""Weekdays inside a term; weekends and holidays have no register to chase."""
	day = getdate(day or nowdate())
	if day.weekday() >= 5:
		return False
	return bool(frappe.db.exists("School Term", {"start_date": ("<=", day), "end_date": (">=", day)}))


def student_attendance(student, from_date=None, to_date=None):
	"""Days marked, attended and absent for one student (portal, report card, student form)."""
	cond, args = "", {"student": student}
	if from_date:
		cond += " and ca.attendance_date >= %(from)s"
		args["from"] = from_date
	if to_date:
		cond += " and ca.attendance_date <= %(to)s"
		args["to"] = to_date
	rows = frappe.db.sql(
		f"""select ca.attendance_date, s.status, s.note from `tabClass Attendance Student` s
		join `tabClass Attendance` ca on ca.name = s.parent
		where s.student = %(student)s {cond} order by ca.attendance_date desc""", args, as_dict=True)
	attended = sum(1 for r in rows if r.status in ATTENDING)
	return {
		"marked": len(rows), "attended": attended, "percent": rate(attended, len(rows)),
		**{s.lower(): sum(1 for r in rows if r.status == s) for s in STATUSES},
		"recent_absences": [{"date": formatdate(r.attendance_date, "EEE d MMM"), "status": r.status, "note": r.note}
							for r in rows if r.status in ("Absent", "Excused")][:5],
	}


@frappe.whitelist()
def student_summary(student, term=None):
	frappe.has_permission("Student", "read", frappe.get_doc("Student", student), throw=True)
	t = frappe.get_cached_doc("School Term", term) if term else None
	if not t:
		from school_erp.school.doctype.school_term.school_term import get_current_term

		t = get_current_term()
	return student_attendance(student, t.start_date if t else None, t.end_date if t else None)
