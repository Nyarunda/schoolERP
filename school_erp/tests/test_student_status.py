"""Bench tests: Transferred / Left / Graduated learners keep when (and where) they went."""

import frappe

from school_erp.tests.test_integration import TestCase, setup_school


class TestStudentStatus(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def test_transfer_needs_school_and_records_date(self):
		s = frappe.get_doc({"doctype": "Student", "first_name": "Halima", "last_name": "Status", "stream": "Grade 4 Test",
							"gender": "Female"}).insert()
		s.status = "Transferred"
		self.assertRaises(frappe.ValidationError, s.save)  # where to?
		s.reload()
		s.update({"status": "Transferred", "transferred_to": "Moi Primary School"})
		s.save()
		self.assertTrue(s.leaving_date)
		s.status = "Graduated"
		s.save()
		self.assertIsNone(s.transferred_to)
		s.status = "Active"  # re-admitted
		s.save()
		self.assertIsNone(s.leaving_date)
