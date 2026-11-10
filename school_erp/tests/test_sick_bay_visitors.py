"""Bench tests: sick bay visits (allergies shown, parents told), visitor book, gate passes, reports."""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from school_erp.tests.test_integration import TestCase, setup_school

SMS_OK = {"sent": ["254712345678"], "failed": []}


class TestSickBayVisitors(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def kid(self, first):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Health", "stream": "Grade 4 Test", "gender": "Female",
			"guardians": [{"guardian_name": "Mama " + first, "relation": "Mother", "mobile_no": "0712345678"}],
		}).insert().name

	def visit(self, student, **kw):
		return frappe.get_doc({"doctype": "Sick Bay Visit", "student": student, "symptoms": "Headache", **kw})

	def test_visit_copies_allergies_and_tells_parent_when_sent_home(self):
		s = self.kid("Akinyi")
		frappe.get_doc({"doctype": "Student Health Record", "student": s, "allergies": "Penicillin"}).insert()
		with patch("school_erp.api.messaging.send_sms", return_value=SMS_OK) as sms:
			calm = self.visit(s, temperature=36.6).insert()
			self.assertFalse(sms.called)  # back to class, no fever: no SMS
			home = self.visit(s, temperature=38.4, outcome="Sent home").insert()
			self.assertTrue(sms.called)
		self.assertEqual(calm.allergies, "Penicillin")
		self.assertTrue(frappe.db.get_value("Sick Bay Visit", home.name, "parent_notified"))

	def test_visit_validation(self):
		s = self.kid("Muthoni")
		with self.assertRaises(frappe.ValidationError):
			self.visit(s, temperature=98.6).insert()  # Fahrenheit
		with self.assertRaises(frappe.ValidationError):
			self.visit(s, outcome="Referred to hospital").insert()  # where to?

	def test_visitor_sign_out(self):
		from school_erp.api.health import sign_out_visitor

		v = frappe.get_doc({"doctype": "Visitor Log", "visitor_name": "john  doe", "phone": "0711000222", "purpose": "Delivery",
							"vehicle_registration": "kcz 123a", "time_in": add_to_date(now_datetime(), minutes=-45)}).insert()
		self.assertEqual((v.visitor_name, v.vehicle_registration, v.status), ("John Doe", "KCZ123A", "On premises"))
		out = sign_out_visitor(v.name)
		self.assertEqual(out["status"], "Signed out")
		self.assertGreaterEqual(out["minutes"], 44)

	def test_gate_pass_one_at_a_time(self):
		from school_erp.api.health import gate_pass_returned

		s = self.kid("Njeri")
		with patch("school_erp.api.messaging.send_sms", return_value=SMS_OK):
			gp = frappe.get_doc({"doctype": "Gate Pass", "student": s, "reason": "Appointment", "picked_by_name": "Mama Njeri"}).insert()
		self.assertTrue(frappe.db.get_value("Gate Pass", gp.name, "parent_notified"))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Gate Pass", "student": s, "reason": "Family", "picked_by_name": "Uncle"}).insert()
		gate_pass_returned(gp.name)
		self.assertEqual(frappe.db.get_value("Gate Pass", gp.name, "status"), "Returned")

	def test_reports(self):
		from school_erp.school.report.sick_bay_register.sick_bay_register import execute as register
		from school_erp.school.report.visitor_register.visitor_register import execute as visitors

		s = self.kid("Wanza")
		for _i in range(3):
			self.visit(s).insert()
		_c, freq, *_ = register({"view": "Frequent Visitors", "min_visits": 3})
		self.assertTrue(any(r["student"] == s for r in freq))
		self.assertIsNotNone(visitors({"on_premises": 1}))
