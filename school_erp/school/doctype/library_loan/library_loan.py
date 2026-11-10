# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.library import due_date_for, limit_problem


class LibraryLoan(Document):
	def validate(self):
		from school_erp.api.library import library_settings

		s = library_settings()
		if self.borrower_type == "Student":
			if not self.student:
				frappe.throw(_("Choose the learner"))
			self.teacher = None
			name, cls, status = frappe.db.get_value("Student", self.student, ["student_name", "school_class", "status"])
			self.borrower_name, self.school_class = name, cls
		else:
			if not self.teacher:
				frappe.throw(_("Choose the teacher"))
			self.student = None
			status = "Active" if frappe.db.get_value("Teacher", self.teacher, "is_active") else "Inactive"
			self.borrower_name, self.school_class = frappe.db.get_value("Teacher", self.teacher, "teacher_name"), None
		self.accession_no = (self.accession_no or "").strip().upper()
		if not self.is_new():
			return
		if status != "Active":
			frappe.throw(_("{0} is not an active borrower").format(self.borrower_name))
		copy = frappe.db.get_value("Library Book Copy", {"parent": self.book, "parenttype": "Library Book",
														 "accession_no": self.accession_no}, "status")
		if copy is None:
			frappe.throw(_("{0} is not a copy of this book").format(self.accession_no))
		if copy != "Available":
			frappe.throw(_("Copy {0} is not available ({1})").format(self.accession_no, copy))
		key = {"student": self.student} if self.student else {"teacher": self.teacher}
		open_loans = frappe.db.count("Library Loan", {**key, "status": "On Loan"})
		limit = s.max_books_student if self.borrower_type == "Student" else s.max_books_teacher
		problem = limit_problem(open_loans, limit, self.borrower_name)
		if problem:
			frappe.throw(_(problem))
		days = s.loan_days_student if self.borrower_type == "Student" else s.loan_days_teacher
		self.due_date = self.due_date or due_date_for(self.issue_date, days)
		self.status, self.issued_by = "On Loan", frappe.session.user

	def after_insert(self):
		from school_erp.api.library import set_copy_status

		set_copy_status(self.book, self.accession_no, "On Loan")
