"""Bench tests: library books and copies, issuing rules, returns with fines billed to fees, renewals, lost books."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

from school_erp.tests.test_integration import TestCase, setup_school


class TestLibraryLoans(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.db.set_single_value("Library Settings", {"max_books_student": 1, "fine_per_day": 10, "fine_grace_days": 0,
														"max_fine": 500, "bill_fines_to_fees": 1, "max_renewals": 1,
														"loan_days_student": 14})
		frappe.clear_document_cache("Library Settings", "Library Settings")
		cls.prefix = "T" + frappe.generate_hash(length=4).upper() + "-"
		cls.book = frappe.get_doc({"doctype": "Library Book", "title": "The River and the Source", "category": "Set Book / Literature",
								   "price": 800, "copies": [{"accession_no": cls.prefix + str(i)} for i in range(1, 4)]}).insert().name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def kid(self, first):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Reader", "stream": "Grade 4 Test", "gender": "Female",
			"guardians": [{"guardian_name": "Mama " + first, "relation": "Mother", "mobile_no": "0712345678"}],
		}).insert().name

	def issue(self, student, copy, **kw):
		return frappe.get_doc({"doctype": "Library Loan", "borrower_type": "Student", "student": student, "book": self.book,
							   "accession_no": copy, **kw}).insert()

	def test_copies_unique_and_counted(self):
		self.assertEqual(frappe.db.get_value("Library Book", self.book, ["total_copies", "available_copies"]), (3, 3))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Library Book", "title": "Dup", "copies": [{"accession_no": self.prefix + "1"}]}).insert()

	def test_issue_rules_and_late_return_billed(self):
		from school_erp.api.library import return_book

		s = self.kid("Wairimu")
		loan = self.issue(s, self.prefix.lower() + "1", issue_date=add_days(nowdate(), -20))
		self.assertEqual(str(loan.due_date), add_days(nowdate(), -6))
		self.assertEqual(frappe.db.get_value("Library Book", self.book, "available_copies"), 2)
		with self.assertRaises(frappe.ValidationError):
			self.issue(self.kid("Other"), self.prefix + "1")  # copy is out
		with self.assertRaises(frappe.ValidationError):
			self.issue(s, self.prefix + "2")  # learner limit is 1
		out = return_book(loan.name, "Good")
		self.assertEqual(out["fine"], 60)
		loan.reload()
		self.assertEqual((loan.status, loan.days_overdue), ("Returned", 6))
		inv = frappe.get_doc("Sales Invoice", loan.fine_invoice)
		self.assertEqual((inv.customer, inv.grand_total, inv.school_term), (s, 60, None))
		self.assertEqual(frappe.db.get_value("Library Book", self.book, "available_copies"), 3)

	def test_renew_once_and_lost_book(self):
		from school_erp.api.library import mark_lost, renew_loan

		s = self.kid("Kamau")
		loan = self.issue(s, self.prefix + "3")
		renew_loan(loan.name)
		with self.assertRaises(frappe.ValidationError):
			renew_loan(loan.name)  # one renewal allowed
		mark_lost(loan.name)
		loan.reload()
		self.assertEqual((loan.status, loan.fine_amount), ("Lost", 800))
		self.assertTrue(loan.fine_invoice)
		copies = {c.accession_no: c.status for c in frappe.get_doc("Library Book", self.book).copies}
		self.assertEqual(copies[self.prefix + "3"], "Lost")

	def test_overdue_reminder_and_reports(self):
		from school_erp.api.library import remind_overdue
		from school_erp.school.report.library_circulation.library_circulation import execute as circulation
		from school_erp.school.report.library_overdue_books.library_overdue_books import execute as overdue

		s = self.kid("Otieno")
		loan = self.issue(s, self.prefix + "2", issue_date=add_days(nowdate(), -16))
		with patch("school_erp.api.messaging.send_sms", return_value={"sent": ["x"], "failed": []}):
			remind_overdue()
		self.assertEqual(str(frappe.db.get_value("Library Loan", loan.name, "last_reminder")), nowdate())
		_c, rows, *_ = overdue({})
		self.assertTrue(any(r["name"] == loan.name and r["fine_so_far"] == 20 for r in rows))
		self.assertIsNotNone(circulation({"group_by": "Category"}))
