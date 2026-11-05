# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, getdate, nowdate

from school_erp.logic.attendance import STATUSES, newly_absent, summarise


class ClassAttendance(Document):
	def validate(self):
		day = getdate(self.attendance_date)
		today = getdate(nowdate())
		if day > today:
			frappe.throw(_("You can't take the register for a future date"))
		dup = frappe.db.get_value("Class Attendance", {"stream": self.stream, "attendance_date": day, "name": ("!=", self.name)})
		if dup:
			frappe.throw(_("The register for {0} on {1} is already taken: {2}").format(self.stream, frappe.format(day, "Date"), dup))
		self.check_edit_window(day, today)
		self.school_class = frappe.db.get_value("Stream", self.stream, "school_class")
		self.school_term = frappe.db.get_value(
			"School Term", {"start_date": ("<=", day), "end_date": (">=", day)}, "name") or self.school_term
		self.marked_by = frappe.session.user
		self.teacher = frappe.db.get_value("Teacher", {"user": frappe.session.user}) or self.teacher
		seen = set()
		for r in self.students:
			if r.student in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(r.idx, r.student_name or r.student))
			seen.add(r.student)
			if r.status not in STATUSES:
				r.status = "Present"
			if not r.student_name:
				r.student_name = frappe.db.get_value("Student", r.student, "student_name")
		self.update(summarise([r.status for r in self.students]))

	def check_edit_window(self, day, today):
		from school_erp.api.staff import is_manager

		if is_manager():
			return
		days = cint(frappe.db.get_single_value("School Settings", "attendance_edit_days"))
		if day < add_days(today, -days):
			frappe.throw(_("Registers older than {0} day(s) can only be changed by the Head Teacher or School Admin").format(days)
						 if days else _("Only today's register can be taken or changed. Ask the Head Teacher or School Admin to correct an earlier one."),
						 frappe.PermissionError)

	def before_save(self):
		before = self.get_doc_before_save()
		old = {r.student: r.status for r in (before.students if before else [])}
		self.flags.newly_absent = newly_absent(old, {r.student: r.status for r in self.students})

	def on_update(self):
		from school_erp.api.attendance import queue_absence_sms

		if self.flags.newly_absent:
			queue_absence_sms(self)

	@frappe.whitelist()
	def get_students(self):
		from school_erp.api.attendance import stream_students

		existing = {r.student for r in self.students}
		for s in stream_students(self.stream):
			if s.name not in existing:
				self.append("students", {"student": s.name, "student_name": s.student_name, "status": "Present"})
		return len(self.students)
