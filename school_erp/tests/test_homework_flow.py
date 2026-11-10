"""Bench tests: homework, hand-in tracking, parent SMS once, what the parent portal shows."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

from school_erp.tests.test_integration import TestCase, setup_school


class TestHomeworkFlow(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		cls.subject = frappe.get_all("Subject", pluck="name", limit=1)[0]
		cls.kid = frappe.get_doc({
			"doctype": "Student", "first_name": "Juma", "last_name": "Homework", "stream": "Grade 4 Test", "gender": "Male",
			"guardians": [{"guardian_name": "Baba Juma", "relation": "Father", "mobile_no": "0712345678"}],
		}).insert().name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def homework(self, **kw):
		return frappe.get_doc({"doctype": "Homework", "title": "Fractions worksheet", "subject": self.subject,
							   "stream": "Grade 4 Test", "due_date": add_days(nowdate(), 2),
							   "description": "<p>Do page 12</p>", **kw})

	def test_due_date_before_set_date_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.homework(due_date=add_days(nowdate(), -1)).insert()

	def test_publish_sms_once_and_portal(self):
		from school_erp.api.homework import portal_homework

		hw = self.homework(submissions=[{"student": self.kid, "status": "Submitted"}]).insert()
		self.assertEqual((hw.done_count, hw.completion), (1, 100))
		self.assertEqual(portal_homework(self.kid, "Grade 4 Test"), [])  # drafts are not shown
		with patch("school_erp.api.messaging.send_sms", return_value={"sent": ["x"], "failed": []}) as sms:
			hw.status = "Published"
			hw.save()
			hw.reload()
			self.assertTrue(hw.parents_notified)
			hw.title = "Fractions worksheet (updated)"
			hw.save()  # editing again does not SMS again
		self.assertEqual(sum(1 for c in sms.call_args_list if "homework" in c.args[1]), 1)
		shown = portal_homework(self.kid, "Grade 4 Test")
		self.assertEqual(shown[0]["handed_in"], "Submitted")
		self.assertEqual(shown[0]["due_label"], "Due in 2 days")

	def test_register_report(self):
		from school_erp.school.report.homework_register.homework_register import execute

		self.homework(status="Published", notify_parents=0).insert()
		_c, rows, *_ = execute({"stream": "Grade 4 Test"})
		self.assertTrue(rows)
