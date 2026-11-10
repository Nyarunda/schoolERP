# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from school_erp.api.exams import scale_bands, subject_teacher
from school_erp.logic.exams import grade_for


class ExamMarkSheet(Document):
	def validate(self):
		exam = frappe.get_cached_doc("Exam", self.exam)
		if exam.status == "Published" and not frappe.has_permission("Exam", "write"):
			frappe.throw(_("Results for {0} are published; ask the Head Teacher to reopen marks").format(self.exam))
		classes = [c.school_class for c in exam.classes]
		if self.school_class not in classes:
			frappe.throw(_("{0} is not part of {1}").format(self.stream, self.exam))
		subjects = [s.subject for s in exam.subjects]
		if subjects and self.subject not in subjects:
			frappe.throw(_("{0} is not examined in {1}").format(self.subject, self.exam))
		dup = frappe.db.get_value("Exam Mark Sheet", {"exam": self.exam, "stream": self.stream, "subject": self.subject,
													 "docstatus": ("<", 2), "name": ("!=", self.name)})
		if dup:
			frappe.throw(_("Marks for {0} {1} are already in {2}").format(self.stream, self.subject, dup))
		if not self.teacher:
			t = subject_teacher(self.stream, self.subject, self.school_term)
			self.teacher = (t[0][0] if t else None) or frappe.db.get_value("Teacher", {"user": frappe.session.user})
		self.max_marks = flt(self.max_marks) or flt(exam.max_marks) or 100
		bands = scale_bands(exam.grading_scale)
		seen, values = set(), []
		for m in self.marks:
			if m.student in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(m.idx, m.student_name or m.student))
			seen.add(m.student)
			if m.absent:
				m.marks, m.grade = None, "ABS"
				continue
			raw = (m.marks or "").strip()
			if not raw:
				m.marks, m.grade = None, ""
				continue
			try:
				val = float(raw)
			except ValueError:
				frappe.throw(_("Row {0}: '{1}' is not a number").format(m.idx, raw))
			if val < 0 or val > self.max_marks:
				frappe.throw(_("Row {0}: {1} must be between 0 and {2}").format(m.idx, m.student_name, self.max_marks))
			m.marks = f"{val:g}"
			m.grade = grade_for(val / self.max_marks * 100, bands)["grade"]
			values.append(val)
		self.entered = len(values) + sum(1 for m in self.marks if m.absent)
		self.average = round(sum(values) / len(values), 1) if values else 0
		self.highest = max(values) if values else 0
		self.lowest = min(values) if values else 0
		self.title = f"{self.stream} · {self.subject} · {self.exam}"[:140]
		if self.docstatus == 0:
			self.reviewer = approver_for(self.subject)
		self.track_approval()

	def track_approval(self):
		before = self.get_doc_before_save()
		old = before.approval_status if before else None
		if old == self.approval_status:
			return
		if self.approval_status == "Pending Approval":
			self.review_comment = None
			blank = [m.student_name for m in self.marks if not m.absent and not (m.marks or "").strip()]
			if blank:
				frappe.throw(_("Enter marks (or tick Absent) for: {0}").format(", ".join(blank[:10]) + ("..." if len(blank) > 10 else "")),
							 title=_("Marks missing"))
		elif self.approval_status == "Returned" and not (self.review_comment or "").strip():
			frappe.throw(_("Say what needs correcting before returning the mark sheet"), title=_("Reason required"))

	def on_update(self):
		before = self.get_doc_before_save()
		if self.docstatus == 0 and before and before.approval_status != self.approval_status:
			notify_marks_state(self)

	@frappe.whitelist()
	def get_students(self):
		existing = {m.student for m in self.marks}
		for s in frappe.get_all("Student", filters={"stream": self.stream, "status": "Active"},
								fields=["name", "student_name"], order_by="student_name"):
			if s.name not in existing:
				self.append("marks", {"student": s.name, "student_name": s.student_name})
		return len(self.marks)

	def before_submit(self):
		if approval_required():
			before = self.get_doc_before_save()
			# the only way in is the workflow's Approve from Pending Approval (which checks who may approve);
			# a plain Submit would skip the Head of Department
			if not before or before.approval_status != "Pending Approval":
				frappe.throw(_("Send the mark sheet for approval; it is submitted when it is approved."), frappe.PermissionError)
		self.approval_status = "Approved"
		self.approved_by = frappe.session.user
		self.approved_on = now_datetime()
		blank = [m.student_name for m in self.marks if not m.absent and not (m.marks or "").strip()]
		if blank:
			frappe.throw(_("Enter marks (or tick Absent) for: {0}").format(", ".join(blank[:10]) + ("..." if len(blank) > 10 else "")))

	def on_submit(self):
		if approval_required():
			notify_marks_state(self)

	def on_cancel(self):
		if self.approval_status != "Cancelled":
			self.db_set("approval_status", "Cancelled")


def approval_required() -> bool:
	return bool(frappe.db.get_value("Workflow", {"document_type": "Exam Mark Sheet", "is_active": 1}))


def approver_for(subject) -> str | None:
	"""The subject's Head of Department, else the Head Teacher login."""
	return (frappe.db.get_value("Subject", subject, "head_of_department") if subject else None) or \
		frappe.db.get_single_value("School Settings", "head_teacher_user")


def teacher_users(doc) -> list[str]:
	users = {doc.owner}
	if doc.teacher:
		users.add(frappe.db.get_value("Teacher", doc.teacher, "user"))
	return [u for u in users if u and u not in ("Administrator", "Guest")]


def notify_marks_state(doc):
	from school_erp.api.notify import notify, users_for_role

	what = f"{doc.stream} · {doc.subject} ({doc.exam})"
	if doc.approval_status == "Pending Approval":
		users = [doc.reviewer] if doc.reviewer else users_for_role("Head Teacher")
		notify(_("Marks to approve: {0}").format(what),
			   _("{0} students, average {1}. Open it and choose Approve or Return.").format(doc.entered, doc.average),
			   users=[u for u in users if u != frappe.session.user], doc=doc, sms=False)
	elif doc.approval_status == "Returned":
		notify(_("Marks returned: {0}").format(what), _("To correct: {0}").format(doc.review_comment or ""),
			   users=teacher_users(doc), doc=doc, sms=False, indicator="red")
	elif doc.approval_status == "Approved":
		notify(_("Marks approved: {0}").format(what), _("Approved by {0}").format(frappe.utils.get_fullname(doc.approved_by)),
			   users=[u for u in teacher_users(doc) if u != frappe.session.user], doc=doc, sms=False, indicator="green")
