"""One place to alert staff: bell notification (+ email per their notification settings) and optional SMS."""

import frappe
from frappe.utils.user import get_users_with_role

from school_erp import licensing


def staff_contact(staff_member: str) -> dict:
	row = frappe.db.get_value("Staff Member", staff_member, ["user", "phone", "full_name"], as_dict=True)
	return row or {}


def users_for_role(role: str) -> list[str]:
	return [u for u in get_users_with_role(role) if u not in ("Administrator", "Guest")]


def staff_for_user(user: str | None = None) -> str | None:
	return frappe.db.get_value("Staff Member", {"user": user or frappe.session.user, "status": ("!=", "Left")})


def notify(subject: str, message: str = "", users=None, staff=None, doc=None, sms: bool = True, sms_text: str | None = None,
		   indicator: str = "blue"):
	"""users: user ids; staff: Staff Member names (their login gets the bell alert, their phone the SMS).
	Every recipient gets: a bell notification (emailed per their notification settings), a live toast if they are
	logged in, and an SMS when SMS is on."""
	users = set(u for u in (users or []) if u)
	phones = []
	for s in staff or []:
		c = staff_contact(s)
		if c.get("user"):
			users.add(c["user"])
		if c.get("phone"):
			phones.append(c["phone"])
	for u in list(users):
		phone = frappe.db.get_value("Staff Member", {"user": u}, "phone") or frappe.db.get_value("User", u, "mobile_no")
		if phone:
			phones.append(phone)

	if users and not frappe.flags.in_install:
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		payload = {"type": "Alert", "subject": subject, "email_content": message or subject}
		if doc is not None:
			payload.update(document_type=doc.doctype, document_name=doc.name)
		try:
			enqueue_create_notification(sorted(users), payload)
		except Exception:
			frappe.log_error(title="School notification failed")
		toast = {"title": subject, "message": (message or "")[:220], "indicator": indicator}
		if doc is not None:
			toast.update(doctype=doc.doctype, name=doc.name)
		for u in users:
			frappe.publish_realtime("school_toast", toast, user=u, after_commit=True)

	settings = frappe.get_cached_doc("School Settings")
	if sms and phones and settings.notify_staff_by_sms and licensing.is_enabled("messaging"):
		from school_erp.api.messaging import send_sms

		text = sms_text or subject
		if settings.school_name and settings.school_name not in text:
			text = f"{text} - {settings.school_name}"
		try:
			send_sms(sorted(set(phones)), text[:459])
		except Exception:
			frappe.log_error(title="School staff SMS failed")
