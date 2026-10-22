# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

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

	@frappe.whitelist()
	def get_students(self):
		existing = {m.student for m in self.marks}
		for s in frappe.get_all("Student", filters={"stream": self.stream, "status": "Active"},
								fields=["name", "student_name"], order_by="student_name"):
			if s.name not in existing:
				self.append("marks", {"student": s.name, "student_name": s.student_name})
		return len(self.marks)

	def before_submit(self):
		blank = [m.student_name for m in self.marks if not m.absent and not (m.marks or "").strip()]
		if blank:
			frappe.throw(_("Enter marks (or tick Absent) for: {0}").format(", ".join(blank[:10]) + ("..." if len(blank) > 10 else "")))
