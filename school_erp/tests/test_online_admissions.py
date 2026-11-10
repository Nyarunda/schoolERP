"""Bench tests: admission applications, the public form rules, admitting an applicant as a Student."""

from unittest.mock import patch

import frappe

from school_erp.tests.test_integration import TestCase, setup_school


class TestOnlineAdmissions(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.db.set_single_value("Admission Settings", {"accepting_applications": 1, "daily_limit_per_phone": 2})
		frappe.clear_document_cache("Admission Settings", "Admission Settings")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def application(self, phone="0722000111", **kw):
		return frappe.get_doc({
			"doctype": "Admission Application", "first_name": "wanjiru", "last_name": "test", "gender": "Female",
			"date_of_birth": "2017-03-01", "applying_for_class": "Grade 4", "guardian_name": "grace test",
			"relation": "Mother", "guardian_phone": phone, **kw,
		})

	def test_status_rules(self):
		app = self.application().insert()
		self.assertEqual((app.applicant_name, app.status), ("Wanjiru Test", "Received"))
		app.status = "Admitted"  # only through Admit as Student
		self.assertRaises(frappe.ValidationError, app.save)
		app.reload()
		app.status = "Interview Scheduled"  # needs a date
		self.assertRaises(frappe.ValidationError, app.save)
		app.reload()
		app.status = "Rejected"  # needs a reason
		self.assertRaises(frappe.ValidationError, app.save)

	def test_guest_cannot_set_office_fields_and_is_rate_limited(self):
		phone = "07" + frappe.generate_hash(length=8).translate(str.maketrans("abcdef", "123456"))[:8]
		frappe.set_user("Guest")
		try:
			app = self.application(phone=phone, status="Offered", decision_notes="hack", source="Office")
			app.insert(ignore_permissions=True)
			self.assertEqual((app.status, app.source, app.decision_notes), ("Received", "Web Form", None))
			self.application(phone=phone).insert(ignore_permissions=True)
			with self.assertRaises(frappe.ValidationError):
				self.application(phone=phone).insert(ignore_permissions=True)  # limit is 2 a day
		finally:
			frappe.set_user("Administrator")

	def test_defaults_apply_before_settings_are_saved(self):
		from school_erp.api.singles import get_settings

		frappe.db.delete("Singles", {"doctype": "Admission Settings", "field": "received_sms"})
		frappe.clear_document_cache("Admission Settings", "Admission Settings")
		self.assertIn("{ref}", get_settings("Admission Settings").received_sms)

	def test_closed_form_refuses_guests(self):
		frappe.db.set_single_value("Admission Settings", "accepting_applications", 0)
		frappe.clear_document_cache("Admission Settings", "Admission Settings")
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				self.application(phone="0733000999").insert(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("Admission Settings", "accepting_applications", 1)
			frappe.clear_document_cache("Admission Settings", "Admission Settings")

	def test_admit_creates_student_once(self):
		from school_erp.api.admissions import admit, application_status

		app = self.application(phone="0744000222", boarding_type="Day").insert()
		with self.assertRaises(frappe.ValidationError):
			admit(app.name, "Grade 4 Test")  # not offered yet
		app.status = "Offered"
		app.save()
		with patch("school_erp.api.messaging.send_sms", return_value={"sent": ["x"], "failed": []}):
			out = admit(app.name, "Grade 4 Test")
		student = frappe.get_doc("Student", out["student"])
		self.assertEqual((student.first_name, student.stream, student.guardians[0].mobile_no), ("Wanjiru", "Grade 4 Test", "0744000222"))
		app.reload()
		self.assertEqual((app.status, app.student), ("Admitted", student.name))
		self.assertTrue(admit(app.name, "Grade 4 Test")["existing"])  # a second click does not make a twin

		self.assertFalse(application_status(app.name, "0700000000")["found"])
		status = application_status(app.name, "254744000222")
		self.assertEqual((status["found"], status["status"]), (True, "Admitted"))

	def test_pipeline_report(self):
		from school_erp.school.report.admissions_pipeline.admissions_pipeline import execute

		self.application(phone="0755000333").insert()
		_c, rows, _m, _chart, summary = execute({})
		self.assertTrue(any(r["applying_for_class"] == "Grade 4" for r in rows))
		self.assertGreaterEqual(summary[0]["value"], 1)
