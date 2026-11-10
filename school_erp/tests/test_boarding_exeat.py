"""Bench tests: dormitories, bed allocation rules, exeat approval and gate check-out/in, late alerts."""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from school_erp.tests.test_integration import TestCase, setup_school


class TestBoardingExeat(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		suffix = frappe.generate_hash(length=4)
		cls.girls = frappe.get_doc({"doctype": "Dormitory", "dormitory_name": f"Girls {suffix}", "gender": "Girls",
									"capacity": 2, "house_parent": "Administrator"}).insert().name
		cls.boys = frappe.get_doc({"doctype": "Dormitory", "dormitory_name": f"Boys {suffix}", "gender": "Boys",
								   "capacity": 5}).insert().name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def boarder(self, first, gender="Female", boarding_type="Boarder"):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Boarder", "stream": "Grade 4 Test", "gender": gender,
			"boarding_type": boarding_type,
			"guardians": [{"guardian_name": "Parent " + first, "relation": "Mother", "mobile_no": "0712345678"}],
		}).insert().name

	def allocate(self, student, dorm, bed=None):
		return frappe.get_doc({"doctype": "Boarding Allocation", "student": student, "dormitory": dorm, "bed_number": bed}).insert()

	def test_allocation_rules_and_counts(self):
		a = self.boarder("Amina")
		b = self.boarder("Beth")
		c = self.boarder("Carol")
		with self.assertRaises(frappe.ValidationError):
			self.allocate(self.boarder("Dan", gender="Male"), self.girls)  # wrong dormitory
		with self.assertRaises(frappe.ValidationError):
			self.allocate(self.boarder("Day", boarding_type="Day"), self.girls)  # day scholar
		self.allocate(a, self.girls, "b1")
		with self.assertRaises(frappe.ValidationError):
			self.allocate(b, self.girls, "B1")  # bed taken (stored upper case)
		self.allocate(b, self.girls, "B2")
		with self.assertRaises(frappe.ValidationError):
			self.allocate(c, self.girls)  # capacity 2
		with self.assertRaises(frappe.ValidationError):
			self.allocate(a, self.boys)  # already has a bed
		self.assertEqual(frappe.db.get_value("Dormitory", self.girls, ["occupied", "free_beds"]), (2, 0))

	def test_exeat_flow_with_sms(self):
		from school_erp.api import boarding

		kid = self.boarder("Eve")
		e = frappe.get_doc({"doctype": "Exeat", "student": kid, "exeat_type": "Weekend", "reason": "Family visit",
							"departure": now_datetime(), "expected_return": add_to_date(now_datetime(), hours=48),
							"status": "Out"}).insert()
		self.assertEqual(e.status, "Requested")  # can't be created already out
		with self.assertRaises(frappe.ValidationError):
			boarding.check_out(e.name, "Mama Eve")  # not approved yet
		with patch("school_erp.api.messaging.send_sms", return_value={"sent": ["x"], "failed": []}) as sms:
			boarding.approve_exeat(e.name)
			boarding.check_out(e.name, "Mama Eve", "Mother", "12345678", "0712345678")
			boarding.check_in(e.name)
		e.reload()
		self.assertEqual((e.status, e.picked_by_name, e.minutes_late), ("Returned", "Mama Eve", 0))
		self.assertGreaterEqual(sms.call_count, 3)

	def test_one_open_exeat_and_overdue_alert(self):
		from school_erp.api import boarding

		kid = self.boarder("Faith")
		past = add_to_date(now_datetime(), hours=-5)
		e = frappe.get_doc({"doctype": "Exeat", "student": kid, "exeat_type": "Medical", "reason": "Clinic",
							"departure": add_to_date(past, hours=-1), "expected_return": past}).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Exeat", "student": kid, "exeat_type": "Weekend", "reason": "Again",
							"departure": now_datetime(), "expected_return": add_to_date(now_datetime(), hours=3)}).insert()
		boarding.approve_exeat(e.name)
		boarding.check_out(e.name, "Uncle")
		with patch("school_erp.api.messaging.send_sms", return_value={"sent": ["x"], "failed": []}):
			boarding.alert_overdue_exeats()
		self.assertTrue(frappe.db.get_value("Exeat", e.name, "overdue_alerted"))

	def test_reports(self):
		from school_erp.school.report.dormitory_occupancy.dormitory_occupancy import execute as occupancy
		from school_erp.school.report.exeat_register.exeat_register import execute as register

		_c, rows, *_ = occupancy({})
		self.assertTrue(any(r["dormitory"] == self.girls for r in rows))
		self.assertIsNotNone(register({"out_now": 1}))
