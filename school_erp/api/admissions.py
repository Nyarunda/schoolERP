"""Online admissions: public application form, SMS to the parent, admitting an applicant as a Student."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, format_datetime, formatdate, get_url, nowdate

from school_erp import licensing
from school_erp.logic.admissions import ADMIT_FROM, OPEN
from school_erp.logic.text import normalize_phone, render

# Student fields filled from the application when this site's Student has them
OPTIONAL_STUDENT_FIELDS = ("birth_certificate_no", "previous_school")


def settings():
	from school_erp.api.singles import get_settings

	return get_settings("Admission Settings")


def check_open_and_rate_limit(phone):
	"""Guards the public form: applications must be open, and one phone number can't flood the office."""
	licensing.require("admissions")
	s = settings()
	if not cint(s.accepting_applications):
		frappe.throw(_(s.closed_message or "We are not taking applications online right now."))
	if not phone:
		frappe.throw(_("Please give a phone number so we can update you"))
	cc = frappe.db.get_single_value("School Settings", "country_code") or "254"
	mine = normalize_phone(phone, cc)
	if not mine:
		frappe.throw(_("Please give a valid phone number"))
	today = frappe.get_all("Admission Application", filters={"creation": (">=", nowdate())}, pluck="guardian_phone")
	if sum(1 for p in today if normalize_phone(p, cc) == mine) >= (cint(s.daily_limit_per_phone) or 3):
		frappe.throw(_("Too many applications from this number today. Please call the school office."))


def status_url():
	return get_url("/admission-status")


def sms_applicant(doc, template_field, **extra):
	if not doc.guardian_phone or not licensing.is_enabled("messaging"):
		return
	template = settings().get(template_field)
	if not template:
		return
	from school_erp.api.messaging import send_sms

	text = render(template, {
		"guardian_name": (doc.guardian_name or "").split(" ")[0], "applicant": doc.first_name, "ref": doc.name,
		"class_name": doc.applying_for_class, "url": status_url(),
		"interview_date": format_datetime(doc.interview_date, "d MMM yyyy, h:mm a") if doc.interview_date else "",
		"school_name": frappe.db.get_single_value("School Settings", "school_name") or "", **extra,
	})
	try:
		send_sms([doc.guardian_phone], text)
	except Exception:
		frappe.log_error(title=f"Admission SMS failed: {doc.name}")


def alert_office(doc):
	from school_erp.api.notify import notify, users_for_role

	role = settings().notify_role or "School Admin"
	notify(_("New admission application {0}: {1} for {2}").format(doc.name, doc.applicant_name, doc.applying_for_class),
		   _("Parent: {0}, {1}").format(doc.guardian_name, doc.guardian_phone), users=users_for_role(role), doc=doc, sms=False)


@frappe.whitelist(methods=["POST"])
def admit(application, stream):
	"""Create the Student (with the parent as primary guardian) from an offered/accepted application."""
	licensing.require("admissions")
	app = frappe.get_doc("Admission Application", application)
	frappe.has_permission("Admission Application", "write", app, throw=True)
	frappe.has_permission("Student", "create", throw=True)
	if app.student:
		return {"student": app.student, "existing": True}
	if app.status not in ADMIT_FROM:
		frappe.throw(_("Only an Offered or Accepted application can be admitted (this one is {0})").format(app.status))
	student = frappe.get_doc({
		"doctype": "Student", "first_name": app.first_name, "middle_name": app.middle_name, "last_name": app.last_name,
		"gender": app.gender, "date_of_birth": app.date_of_birth, "stream": stream, "boarding_type": app.boarding_type or "Day",
		"admission_date": nowdate(), "status": "Active",
		"guardians": [{"guardian_name": app.guardian_name, "relation": app.relation or "Guardian", "mobile_no": app.guardian_phone,
					   "email": app.guardian_email, "is_primary": 1, "receive_sms": 1, "receive_email": 1 if app.guardian_email else 0}],
	})
	meta = frappe.get_meta("Student")
	for field in OPTIONAL_STUDENT_FIELDS:
		if meta.has_field(field) and app.get(field):
			student.set(field, app.get(field))
	if meta.has_field("special_needs") and (app.special_needs_details or "").strip():
		student.special_needs = 1
		student.special_needs_details = app.special_needs_details
	student.insert()
	app.flags.admitting = True
	app.update({"status": "Admitted", "student": student.name, "assigned_stream": stream, "admitted_on": nowdate()})
	app.save()
	sms_applicant(app, "admitted_sms", student_id=student.name)
	return {"student": student.name}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=20, seconds=60 * 60)
@licensing.licensed("Admission Application")
def application_status(ref, phone):
	"""Public lookup. Needs the reference AND the parent's phone, and reveals only the status and dates."""
	ref = (ref or "").strip().upper()
	row = frappe.db.get_value("Admission Application", ref,
							  ["name", "guardian_phone", "status", "first_name", "applying_for_class", "creation", "interview_date"],
							  as_dict=True)
	cc = frappe.db.get_single_value("School Settings", "country_code") or "254"
	if not row or not row.guardian_phone or normalize_phone(row.guardian_phone, cc) != normalize_phone(phone, cc):
		return {"found": False}
	shown = {"Received": "Received", "Under Review": "Under review", "Interview Scheduled": "Interview scheduled",
			 "Offered": "Place offered", "Accepted": "Offer accepted", "Admitted": "Admitted", "Rejected": "Not successful",
			 "Withdrawn": "Withdrawn"}
	return {
		"found": True, "ref": row.name, "applicant": row.first_name, "class_name": row.applying_for_class,
		"status": row.status, "status_label": _(shown.get(row.status, row.status)), "open": row.status in OPEN,
		"received": formatdate(row.creation, "d MMM yyyy"),
		"interview": format_datetime(row.interview_date, "d MMM yyyy, h:mm a") if row.interview_date and row.status == "Interview Scheduled" else None,
	}
