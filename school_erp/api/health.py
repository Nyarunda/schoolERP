"""Sick bay, visitor book and gate passes: SMS to parents, alerts, signing visitors out."""

import frappe
from frappe import _
from frappe.utils import format_datetime, now_datetime

from school_erp import licensing
from school_erp.logic.health import parent_must_know


def _school():
	return frappe.db.get_single_value("School Settings", "school_name") or ""


def _sms(student_name_or_doc, template, extra):
	"""SMS the learner's guardians; returns the messaging result (or None without the messaging module)."""
	if not licensing.is_enabled("messaging"):
		return None
	from school_erp.api.messaging import sms_student

	student = frappe.get_doc("Student", student_name_or_doc)
	return sms_student(student, template, {"student_name": student.first_name, "school_name": _school(), **extra})


VISIT_TEXT = {
	"Sent home": "Dear {guardian_name}, {student_name} was seen at the school sick bay ({symptoms}){temp} and needs to go home. Please arrange collection. - {school_name}",
	"Referred to hospital": "Dear {guardian_name}, {student_name} was seen at the school sick bay ({symptoms}){temp} and has been referred to {referred_to}. Please call the school. - {school_name}",
	"default": "Dear {guardian_name}, {student_name} was seen at the school sick bay today ({symptoms}){temp}. Outcome: {outcome}. - {school_name}",
}


def _visit_message(doc):
	text = VISIT_TEXT.get(doc.outcome) or VISIT_TEXT["default"]
	temp = f", temperature {doc.temperature:g} °C" if doc.temperature else ""
	return text, {"symptoms": (doc.symptoms or "")[:60], "temp": temp, "referred_to": doc.referred_to or "a clinic",
				  "outcome": (doc.outcome or "").lower()}


def after_visit(doc):
	"""Parents hear straight away when a learner is sent home, referred, or has a fever; the head teacher when referred."""
	if parent_must_know(doc.outcome, doc.temperature):
		_notify_parent(doc)
	if doc.outcome == "Referred to hospital":
		from school_erp.api.notify import notify
		from school_erp.api.staff import head_teacher_users

		notify(_("Referred to hospital: {0}").format(doc.student_name), _("{0} → {1}").format(doc.symptoms, doc.referred_to),
			   users=head_teacher_users(), doc=doc, indicator="red")


def _notify_parent(doc):
	text, extra = _visit_message(doc)
	try:
		result = _sms(doc.student, text, extra)
	except Exception:
		frappe.log_error(title=f"Sick bay SMS failed: {doc.name}")
		return {"sent": 0}
	if result and result.get("sent"):
		frappe.db.set_value("Sick Bay Visit", doc.name, {"parent_notified": 1, "parent_notified_on": now_datetime()},
							update_modified=False)
	return {"sent": len((result or {}).get("sent", []))}


@frappe.whitelist(methods=["POST"])
def sms_parent_about_visit(name):
	licensing.require("health")
	licensing.require("messaging")
	doc = frappe.get_doc("Sick Bay Visit", name)
	frappe.has_permission("Sick Bay Visit", "write", doc, throw=True)
	return _notify_parent(doc)


@frappe.whitelist(methods=["POST"])
def sign_out_visitor(name):
	licensing.require("health")
	doc = frappe.get_doc("Visitor Log", name)
	frappe.has_permission("Visitor Log", "write", doc, throw=True)
	if doc.time_out:
		return {"status": doc.status}
	doc.time_out = now_datetime()
	doc.save()
	return {"status": doc.status, "minutes": doc.minutes_on_premises}


def sms_gate_pass(doc):
	text = ("Dear {guardian_name}, {student_name} left school at {time} with {picked_by} ({reason}){back}. - {school_name}")
	back = f", expected back {format_datetime(doc.expected_back, 'h:mm a')}" if doc.expected_back else ""
	try:
		result = _sms(doc.student, text, {"time": format_datetime(doc.time_out, "h:mm a"), "picked_by": doc.picked_by_name,
										  "reason": (doc.reason or "").lower(), "back": back})
		if result and result.get("sent"):
			frappe.db.set_value("Gate Pass", doc.name, "parent_notified", 1, update_modified=False)
	except Exception:
		frappe.log_error(title=f"Gate pass SMS failed: {doc.name}")


@frappe.whitelist(methods=["POST"])
def gate_pass_returned(name):
	licensing.require("health")
	doc = frappe.get_doc("Gate Pass", name)
	frappe.has_permission("Gate Pass", "write", doc, throw=True)
	if doc.status == "Returned":
		return {"status": doc.status}
	doc.time_back = now_datetime()
	doc.save()
	return {"status": doc.status}
