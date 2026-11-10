"""Bench tests: government learner IDs on the Student and the NEMIS Census report."""

import frappe

from school_erp.tests.test_integration import TestCase, setup_school


class TestNemisIds(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def make_student(self, first, **kw):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Nemis", "stream": "Grade 4 Test", "gender": "Female",
			"guardians": [{"guardian_name": "Mama " + first, "relation": "Mother", "mobile_no": "0712345678"}], **kw,
		}).insert()

	def test_ids_are_cleaned_and_unique(self):
		upi = "N" + frappe.generate_hash(length=7).upper()
		s = self.make_student("Upi", upi_number=f" {upi[:3].lower()} {upi[3:]} ", birth_certificate_no="bc 1234567")
		self.assertEqual(s.upi_number, upi)
		self.assertEqual(s.birth_certificate_no, "BC1234567")
		with self.assertRaises(frappe.ValidationError):
			self.make_student("Twin", upi_number=upi)
		with self.assertRaises(frappe.ValidationError):
			self.make_student("Bad", upi_number="A$")

	def test_special_needs_details_cleared_when_unticked(self):
		s = self.make_student("Needs", special_needs=1, special_needs_details="Low vision")
		s.special_needs = 0
		s.save()
		self.assertFalse(s.special_needs_details)

	def test_census_report_views(self):
		from school_erp.school.report.nemis_census.nemis_census import execute

		self.make_student("Census")  # no UPI: shows as missing
		columns, rows, _msg, _chart, summary = execute({"view": "Learner List", "missing_only": 1})
		self.assertTrue(any("UPI" in r["missing"] for r in rows))
		self.assertTrue(summary[1]["value"] >= 1)
		_c, by_class, *_ = execute({"view": "Class Summary"})
		self.assertTrue(any(r["school_class"] == "Grade 4" for r in by_class))
		_c, by_age, *_ = execute({"view": "Age & Gender"})
		self.assertTrue(by_age)
