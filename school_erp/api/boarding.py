"""Boarding: dormitory counts, exeat approval and gate check-out/check-in with SMS to parents, late-return alerts."""

import frappe
from frappe import _
from frappe.utils import format_datetime, now_datetime

from school_erp import licensing
from school_erp.logic.boarding import is_overdue, minutes_late
from school_erp.logic.boarding import occupancy as _occupancy

APPROVER_ROLES = {"System Manager", "School Admin", "Head Teacher"}


# ----------------------------------------------------------------------------- dormitories
def active_count(dormitory, exclude=None) -> int:
	filters = {"dormitory": dormitory, "status": "Active"}
	if exclude:
		filters["name"] = ("!=", exclude)
	return frappe.db.count("Boarding Allocation", filters)


def refresh_dormitory(dormitory, exclude=None):
	if not dormitory or not frappe.db.exists("Dormitory", dormitory):
		return
	capacity = frappe.db.get_value("Dormitory", dormitory, "capacity")
	o = _occupancy(capacity, active_count(dormitory, exclude))
	frappe.db.set_value("Dormitory", dormitory, {"occupied": o["occupied"], "free_beds": o["free"]}, update_modified=False)


# ----------------------------------------------------------------------------- exeat actions
def _house_parent(doc):
	return frappe.db.get_value("Dormitory", doc.dormitory, "house_parent") if doc.dormitory else None


def _can_approve(doc) -> bool:
	return bool(APPROVER_ROLES & set(frappe.get_roles())) or frappe.session.user == _house_parent(doc)


def _load(name, need="write"):
	licensing.require("boarding")
	doc = frappe.get_doc("Exeat", name)
	frappe.has_permission("Exeat", need, doc, throw=True)
	return doc


def _save(doc, **values):
	doc.update(values)
	doc.flags.from_action = True
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def approve_exeat(name):
	doc = _load(name)
	if not _can_approve(doc):
		frappe.throw(_("Only the Head Teacher, a School Admin or the dormitory's house parent can approve an exeat"),
					 frappe.PermissionError)
	out = _save(doc, status="Approved", approved_by=frappe.session.user, approved_on=now_datetime())
	sms_parents(doc, "approved")
	return out


@frappe.whitelist(methods=["POST"])
def reject_exeat(name, note):
	doc = _load(name)
	if not _can_approve(doc):
		frappe.throw(_("Only the Head Teacher, a School Admin or the dormitory's house parent can reject an exeat"),
					 frappe.PermissionError)
	if not (note or "").strip():
		frappe.throw(_("Give the reason"))
	return _save(doc, status="Rejected", decision_note=note.strip()[:500])


@frappe.whitelist(methods=["POST"])
def cancel_exeat(name):
	return _save(_load(name), status="Cancelled")


@frappe.whitelist(methods=["POST"])
def check_out(name, picked_by_name, picked_by_relation=None, picked_by_id=None, picked_by_phone=None):
	"""At the gate: who collected the learner, and when. The parents get an SMS."""
	doc = _load(name)
	if not (picked_by_name or "").strip():
		frappe.throw(_("Record who collected the learner"))
	out = _save(doc, status="Out", actual_departure=now_datetime(), checked_out_by=frappe.session.user,
				picked_by_name=picked_by_name.strip(), picked_by_relation=picked_by_relation or doc.picked_by_relation,
				picked_by_id=(picked_by_id or "").strip() or doc.picked_by_id,
				picked_by_phone=(picked_by_phone or "").strip() or doc.picked_by_phone)
	sms_parents(doc, "out")
	return out


@frappe.whitelist(methods=["POST"])
def check_in(name):
	doc = _load(name)
	now = now_datetime()
	out = _save(doc, status="Returned", actual_return=now, checked_in_by=frappe.session.user,
				minutes_late=minutes_late(doc.expected_return, now))
	sms_parents(doc, "returned")
	return out


# ----------------------------------------------------------------------------- messages
TEXTS = {
	"approved": "Dear {guardian_name}, {student_name}'s exeat ({type}) is approved: leaving {departure}, back by {back_by}. - {school_name}",
	"out": "Dear {guardian_name}, {student_name} left school at {time}, collected by {picked_by}. Please return by {back_by}. - {school_name}",
	"returned": "Dear {guardian_name}, {student_name} is back at school ({time}). Thank you. - {school_name}",
	"overdue": "Dear {guardian_name}, {student_name} was due back at school by {back_by} and has not checked in. Please call the school. - {school_name}",
}


def sms_parents(doc, event):
	if not licensing.is_enabled("messaging"):
		return
	from school_erp.api.messaging import sms_student

	fmt = "EEE d MMM, h:mm a"
	try:
		student = frappe.get_doc("Student", doc.student)
		sms_student(student, TEXTS[event], {
			"student_name": student.first_name, "type": (doc.exeat_type or "").lower(),
			"departure": format_datetime(doc.departure, fmt), "back_by": format_datetime(doc.expected_return, fmt),
			"time": format_datetime(now_datetime(), "h:mm a"), "picked_by": doc.picked_by_name or "",
			"school_name": frappe.db.get_single_value("School Settings", "school_name") or "",
		})
	except Exception:
		frappe.log_error(title=f"Exeat SMS failed: {doc.name}")


def alert_approvers(doc):
	from school_erp.api.notify import notify
	from school_erp.api.staff import head_teacher_users

	users = set(head_teacher_users())
	hp = _house_parent(doc)
	if hp:
		users.add(hp)
	notify(_("Exeat request: {0} ({1})").format(doc.student_name, doc.exeat_type),
		   _("Leaving {0}, back by {1}. Reason: {2}").format(format_datetime(doc.departure, "EEE d MMM h:mm a"),
															 format_datetime(doc.expected_return, "EEE d MMM h:mm a"), doc.reason or ""),
		   users=sorted(users), doc=doc, sms=False)


def alert_overdue_exeats():
	"""Hourly: learners still out an hour after they were due back -> house parent, head teacher and the parents, once."""
	if not licensing.is_enabled("boarding"):
		return
	from school_erp.api.notify import notify
	from school_erp.api.staff import head_teacher_users

	now = now_datetime()
	for e in frappe.get_all("Exeat", filters={"status": "Out", "overdue_alerted": 0, "expected_return": ("<", now)},
							fields=["name", "expected_return"]):
		if not is_overdue(e.expected_return, now):
			continue
		doc = frappe.get_doc("Exeat", e.name)
		users = set(head_teacher_users())
		hp = _house_parent(doc)
		if hp:
			users.add(hp)
		try:
			notify(_("Not back from exeat: {0}").format(doc.student_name),
				   _("Was due back {0}. Collected by {1} ({2}).").format(format_datetime(doc.expected_return, "EEE d MMM h:mm a"),
																		 doc.picked_by_name or "-", doc.picked_by_phone or "-"),
				   users=sorted(users), doc=doc, indicator="red")
			sms_parents(doc, "overdue")
		finally:
			frappe.db.set_value("Exeat", doc.name, "overdue_alerted", 1, update_modified=False)
			frappe.db.commit()
