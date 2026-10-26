"""SMS and email to parents. The SMS provider is chosen per school in School Settings."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate

from school_erp import licensing
from school_erp.api.payments import party_balance
from school_erp.logic.paybill import pay_line
from school_erp.logic.text import normalize_phone, render


# ----------------------------------------------------------------------------- providers
def send_sms(numbers: list[str], message: str) -> dict:
	"""Send one message to several numbers. Returns {"sent": [...], "failed": [...]}."""
	licensing.require("messaging")
	settings = frappe.get_cached_doc("School Settings")
	clean = sorted({n for n in (normalize_phone(x, settings.country_code) for x in numbers) if n})
	if not clean:
		return {"sent": [], "failed": list(numbers)}

	provider = settings.sms_provider or "Frappe SMS Settings"
	if provider == "Africa's Talking":
		return _send_africastalking(settings, clean, message)
	if provider == "Custom Hook":
		hooks = frappe.get_hooks("school_sms_sender")
		if not hooks:
			frappe.throw(_("SMS Provider is 'Custom Hook' but no app defines school_sms_sender"))
		return frappe.get_attr(hooks[-1])(clean, message)
	return _send_frappe(clean, message)


def _send_frappe(numbers, message):
	from frappe.core.doctype.sms_settings.sms_settings import send_sms as frappe_send_sms

	try:
		frappe_send_sms(numbers, message, success_msg=False)
		return {"sent": numbers, "failed": []}
	except Exception:
		frappe.log_error(title="School SMS failed")
		return {"sent": [], "failed": numbers}


def _send_africastalking(settings, numbers, message):
	import requests

	api_key = settings.get_password("at_api_key", raise_exception=False)
	if not (settings.at_username and api_key):
		frappe.throw(_("Set the Africa's Talking username and API key in School Settings"))
	host = "api.sandbox.africastalking.com" if settings.at_sandbox else "api.africastalking.com"
	data = {"username": settings.at_username, "to": ",".join("+" + n for n in numbers), "message": message}
	if settings.at_sender_id:
		data["from"] = settings.at_sender_id
	sent, failed = [], []
	try:
		r = requests.post(
			f"https://{host}/version1/messaging",
			data=data,
			headers={"apiKey": api_key, "Accept": "application/json"},
			timeout=30,
		)
		r.raise_for_status()
		for rec in r.json().get("SMSMessageData", {}).get("Recipients", []):
			num = rec.get("number", "").lstrip("+")
			(sent if rec.get("statusCode") in (100, 101, 102) else failed).append(num)
	except Exception:
		frappe.log_error(title="Africa's Talking SMS failed")
		failed = numbers
	_log_sms(sent, message)
	return {"sent": sent, "failed": failed}


def _log_sms(numbers, message):
	if not numbers:
		return
	try:
		frappe.get_doc(
			{
				"doctype": "SMS Log",
				"sender_name": frappe.session.user,
				"sent_on": frappe.utils.nowdate(),
				"message": message,
				"no_of_requested_sms": len(numbers),
				"requested_numbers": "\n".join(numbers),
				"no_of_sent_sms": len(numbers),
				"sent_to": "\n".join(numbers),
			}
		).insert(ignore_permissions=True)
	except Exception:
		pass


# ----------------------------------------------------------------------------- context
def message_context(student_doc, extra=None):
	settings = frappe.get_cached_doc("School Settings")
	currency = settings.currency
	balance = party_balance(student_doc.name)
	ctx = {
		"student_name": student_doc.student_name,
		"first_name": student_doc.first_name,
		"student_id": student_doc.name,
		"class": student_doc.school_class or "",
		"stream": student_doc.stream or "",
		"balance": fmt_money(balance, precision=0, currency=currency),
		"guardian_name": student_doc.primary_guardian or "Parent",
		"school_name": settings.school_name or "",
		"paybill": settings.paybill_number or "",
		"mpesa": pay_line(settings.mpesa_account_type, settings.paybill_number, student_doc.name),
	}
	ctx.update(extra or {})
	return ctx


def _guardians(student_doc, channel):
	from school_erp.school.doctype.student.student import get_guardian_contacts

	return get_guardian_contacts(student_doc, channel)


def sms_student(student_doc, template, extra=None):
	contacts = _guardians(student_doc, "sms")
	if not contacts:
		return {"sent": [], "failed": [], "skipped": True}
	results = {"sent": [], "failed": []}
	for c in contacts:  # personalise the greeting per guardian
		msg = render(template, message_context(student_doc, dict(extra or {}, guardian_name=c["name"])))
		r = send_sms([c["phone"]], msg)
		results["sent"] += r["sent"]
		results["failed"] += r["failed"]
	return results


def email_student(student_doc, subject, body, attach_statement=True):
	from school_erp.api.statement import statement_pdf

	contacts = _guardians(student_doc, "email")
	if not contacts:
		return 0
	ctx = message_context(student_doc)
	attachments = []
	if attach_statement and licensing.is_enabled("fees"):
		attachments.append({"fname": f"Fee Statement {student_doc.name}.pdf", "fcontent": statement_pdf(student_doc.name)})
	frappe.sendmail(
		recipients=[c["email"] for c in contacts],
		subject=render(subject, ctx),
		message=render(body, ctx).replace("\n", "<br>"),
		attachments=attachments,
		reference_doctype="Student",
		reference_name=student_doc.name,
		now=False,
	)
	return len(contacts)


# ----------------------------------------------------------------------------- events
def send_payment_sms(payment):
	fp = frappe.get_doc("Fee Payment", payment)
	settings = frappe.get_cached_doc("School Settings")
	student = frappe.get_doc("Student", fp.student)
	sms_student(
		student,
		settings.payment_sms_template,
		{"amount": fmt_money(fp.amount, precision=0, currency=settings.currency), "reference": fp.reference_no or fp.name},
	)


def notify_billing(term, due_date, students):
	settings = frappe.get_cached_doc("School Settings")
	extra = {"term": term, "due_date": formatdate(due_date, "d MMM yyyy")}
	for name in students:
		try:
			student = frappe.get_doc("Student", name)
			if settings.notify_after_billing and settings.billing_sms_template:
				sms_student(student, settings.billing_sms_template, extra)
			if settings.email_statement_after_billing:
				email_student(student, settings.statement_email_subject, settings.statement_email_body)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Billing notification failed for {name}")


@frappe.whitelist()
def send_statement(student, channel="SMS and Email"):
	"""Button on the Student form."""
	frappe.has_permission("Student", "read", student, throw=True)
	licensing.require("messaging")
	settings = frappe.get_cached_doc("School Settings")
	doc = frappe.get_doc("Student", student)
	out = {"sms": 0, "email": 0}
	if "SMS" in channel:
		out["sms"] = len(sms_student(doc, settings.reminder_sms_template)["sent"])
	if "Email" in channel:
		out["email"] = email_student(doc, settings.statement_email_subject, settings.statement_email_body)
	return out


# ----------------------------------------------------------------------------- bulk messages
def audience_students(msg):
	filters = {"status": "Active"}
	if msg.audience == "Single student":
		return [msg.student] if msg.student else []
	if msg.audience in ("Class", "Students with a balance") and msg.school_class:
		filters["school_class"] = msg.school_class
	if msg.audience in ("Stream", "Students with a balance") and msg.stream:
		filters["stream"] = msg.stream
	names = frappe.get_all("Student", filters=filters, pluck="name", order_by="school_class, student_name")
	if msg.audience == "Students with a balance":
		threshold = max(flt(msg.min_balance), 0.01)
		names = [n for n in names if party_balance(n) >= threshold]
	return names


def process_school_message(name):
	msg = frappe.get_doc("School Message", name)
	msg.db_set("status", "Sending", commit=True)
	students = audience_students(msg)
	sms_sent = emails = failed = 0
	log = []
	for s in students:
		try:
			doc = frappe.get_doc("Student", s)
			if msg.channel in ("SMS", "SMS and Email"):
				r = sms_student(doc, msg.message)
				sms_sent += len(r["sent"])
				failed += len(r["failed"])
				if r.get("skipped"):
					log.append(f"{s}: no SMS contact")
			if msg.channel in ("Email", "SMS and Email"):
				n = email_student(doc, msg.subject, msg.message, attach_statement=msg.attach_statement)
				emails += n
				if not n:
					log.append(f"{s}: no email contact")
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			failed += 1
			log.append(f"{s}: {e}")
	msg.db_set(
		{
			"status": "Sent with Errors" if failed else "Sent",
			"recipients": len(students),
			"sms_sent": sms_sent,
			"emails_sent": emails,
			"failed": failed,
			"log": "\n".join(log) or None,
		},
		commit=True,
	)


@frappe.whitelist()
def preview_audience(name=None, doc=None):
	frappe.has_permission("School Message", "read", throw=True)
	if doc:
		msg = frappe.get_doc(frappe.parse_json(doc))
	else:
		msg = frappe.get_doc("School Message", name)
	students = audience_students(msg)
	sample = []
	for s in students[:5]:
		d = frappe.get_doc("Student", s)
		sample.append({"student": s, "student_name": d.student_name, "text": render(msg.message or "", message_context(d))})
	return {"count": len(students), "sample": sample}
