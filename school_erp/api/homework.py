"""Homework: learners for hand-in tracking, SMS to parents, what the parent portal shows."""

import frappe
from frappe import _
from frappe.utils import formatdate, get_url, getdate, nowdate, strip_html

from school_erp import licensing
from school_erp.logic.homework import due_label, for_parents


@frappe.whitelist()
def stream_students(stream):
	licensing.require("homework")
	frappe.has_permission("Homework", "write", throw=True)
	return frappe.get_all("Student", filters={"stream": stream, "status": "Active"},
						  fields=["name as student", "student_name"], order_by="student_name")


def queue_parent_sms(doc):
	"""Once per homework, after it is published (and only with the messaging module)."""
	if not licensing.is_enabled("messaging"):
		return
	doc.db_set("parents_notified", 1, update_modified=False)
	frappe.enqueue("school_erp.api.homework.send_parent_sms", queue="long", timeout=1800, homework=doc.name,
				   enqueue_after_commit=True, now=bool(frappe.flags.in_test))


def send_parent_sms(homework):
	from school_erp.api.messaging import sms_student

	hw = frappe.get_doc("Homework", homework)
	subject = frappe.db.get_value("Subject", hw.subject, "subject_name") or hw.subject
	school = frappe.db.get_single_value("School Settings", "school_name") or ""
	text = ("Dear {guardian_name}, {student_name} has " + subject + " homework: " + (hw.title or "")[:60] + ", due "
			+ formatdate(hw.due_date, "EEE d MMM") + ". Details: " + get_url("/parent") + " - " + school)
	for name in frappe.get_all("Student", filters={"stream": hw.stream, "status": "Active"}, pluck="name"):
		try:
			student = frappe.get_doc("Student", name)
			sms_student(student, text, {"student_name": student.first_name})
		except Exception:
			frappe.log_error(title=f"Homework SMS failed: {homework} {name}")


def portal_homework(student, stream):
	"""Homework the parent sees for one child: upcoming first, then the last week's, with the child's hand-in status."""
	if not (stream and licensing.is_enabled("homework")):
		return None
	today = getdate(nowdate())
	rows = frappe.get_all("Homework", filters={"stream": stream, "status": "Published"},
						  fields=["name", "title", "subject", "set_on", "due_date", "status", "description", "attachment"],
						  order_by="due_date desc", limit=40)
	shown = for_parents(rows, today)[:12]
	if not shown:
		return []
	names = dict(frappe.get_all("Subject", fields=["name", "subject_name"], as_list=True))
	mine = dict(frappe.get_all("Homework Submission", filters={"parenttype": "Homework", "student": student,
															  "parent": ("in", [h.name for h in shown])},
							   fields=["parent", "status"], as_list=True))
	return [{"title": h.title, "subject": names.get(h.subject, h.subject), "due": formatdate(h.due_date, "EEE d MMM"),
			 "due_label": _(due_label(h.due_date, today)), "overdue": getdate(h.due_date) < today,
			 "text": strip_html(h.description or "")[:600], "attachment": h.attachment, "handed_in": mine.get(h.name)}
			for h in shown]
