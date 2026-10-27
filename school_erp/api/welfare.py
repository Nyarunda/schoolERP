"""Discipline notices to parents and complaint tracking."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import formatdate, get_url

from school_erp import licensing
from school_erp.logic.text import normalize_phone, render


@frappe.whitelist()
def notify_parent_of_incident(name, message=None):
	"""Button on a Discipline Incident: SMS the guardians."""
	licensing.require("welfare")
	licensing.require("messaging")
	doc = frappe.get_doc("Discipline Incident", name)
	frappe.has_permission("Discipline Incident", "write", doc, throw=True)
	from school_erp.api.messaging import sms_student

	student = frappe.get_doc("Student", doc.student)
	school = frappe.db.get_single_value("School Settings", "school_name") or ""
	text = message or (
		f"Dear {{guardian_name}}, this is to inform you that {student.first_name} was involved in a {doc.category.lower()} "
		f"incident on {formatdate(doc.incident_date, 'd MMM')}. Action: {doc.action_taken}. Please contact the school. {school}"
	)
	result = sms_student(student, text)
	if result.get("sent"):
		doc.db_set({"parent_notified": 1, "parent_notified_on": frappe.utils.now_datetime()})
	return {"sent": len(result.get("sent", [])), "failed": len(result.get("failed", []))}


def complaint_status_url():
	return get_url("/complaint-status")


def sms_complainant(doc, template, **extra):
	if not doc.phone or not licensing.is_enabled("messaging"):
		return
	from school_erp.api.messaging import send_sms

	s = frappe.get_cached_doc("School Settings")
	text = render(template or "", {
		"name": (doc.complainant_name or "").split(" ")[0], "ref": doc.name, "url": complaint_status_url(),
		"school_name": s.school_name or "", "resolution": (doc.resolution or "")[:200], **extra,
	})
	try:
		send_sms([doc.phone], text)
	except Exception:
		frappe.log_error(title="Complaint SMS failed")


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=20, seconds=60 * 60)
@licensing.licensed("Complaint")
def complaint_status(ref, phone):
	"""Public status lookup. Needs the reference AND the phone number used, and reveals only status/resolution."""
	ref = (ref or "").strip().upper()
	row = frappe.db.get_value("Complaint", ref, ["name", "phone", "status", "category", "subject", "resolution", "creation", "resolved_on"], as_dict=True)
	cc = frappe.db.get_single_value("School Settings", "country_code") or "254"
	if not row or not row.phone or normalize_phone(row.phone, cc) != normalize_phone(phone, cc):
		return {"found": False}
	return {
		"found": True,
		"ref": row.name,
		"status": row.status,
		"category": row.category,
		"subject": row.subject,
		"received": formatdate(row.creation, "d MMM yyyy"),
		"resolved_on": formatdate(row.resolved_on, "d MMM yyyy") if row.resolved_on else None,
		"resolution": row.resolution if row.status in ("Resolved", "Closed") else None,
	}
