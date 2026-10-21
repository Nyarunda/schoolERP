"""End-to-end tests for staff, leave, expenses, driver logs, duty reports, welfare and reports.

    bench --site test.localhost run-tests --module school_erp.tests.test_operations
"""

import importlib
import os
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from school_erp.tests.test_integration import ALL_MODULES, TestCase, set_license, setup_school

NOTIFY = "frappe.desk.doctype.notification_log.notification_log.enqueue_create_notification"


def next_monday():
	d = getdate(nowdate())
	return add_days(d, 7 - d.weekday())


class TestOperations(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.db.set_single_value("School Settings", "head_teacher_user", "Administrator")
		frappe.db.set_single_value("School Settings", "expense_single_approval_limit", 10000)
		cls.teacher = cls.make_staff("Jane Teacher", "Teaching", "Female")
		cls.reliever = cls.make_staff("Ruth Reliever", "Teaching", "Female")
		cls.driver = cls.make_staff("Dan Driver", "Driver", "Male")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	@classmethod
	def make_staff(cls, name, staff_type, gender):
		email = name.lower().replace(" ", ".") + "@test.school"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": name, "send_welcome_email": 0}).insert(ignore_permissions=True)
		existing = frappe.db.get_value("Staff Member", {"user": email})
		if existing:
			return existing
		return frappe.get_doc({"doctype": "Staff Member", "full_name": name, "staff_type": staff_type, "gender": gender,
							   "phone": "0712000111", "user": email}).insert().name

	# ------------------------------------------------------------------ staff & leave
	def test_staff_gets_teacher_record_and_roles(self):
		sm = frappe.get_doc("Staff Member", self.teacher)
		self.assertTrue(sm.teacher)
		self.assertEqual(frappe.db.get_value("Teacher", sm.teacher, "staff_member"), sm.name)
		roles = frappe.get_roles(sm.user)
		self.assertIn("Staff", roles)
		self.assertIn("Teacher", roles)

	def test_leave_approval_notifies_applicant_and_reliever(self):
		start = next_monday()
		with patch(NOTIFY) as sent:
			la = frappe.get_doc({"doctype": "Leave Application", "staff_member": self.teacher, "leave_type": "Annual Leave",
								 "from_date": start, "to_date": add_days(start, 6), "reason": "Family event", "reliever": self.reliever}).insert()
			self.assertEqual(la.total_days, 5)  # Mon-Sun counts 5 working days
			self.assertEqual(la.status, "Pending Approval")
			self.assertEqual(la.approver, "Administrator")

			from school_erp.api.staff import decide_leave

			self.assertEqual(decide_leave(la.name, "Approved", "Enjoy"), "Approved")
			recipients = [c.args[0] for c in sent.call_args_list]
			subjects = [c.args[1]["subject"] for c in sent.call_args_list]
		la.reload()
		self.assertEqual(la.docstatus, 1)
		self.assertTrue(any("jane.teacher@test.school" in r for r in recipients))
		self.assertTrue(any("ruth.reliever@test.school" in r for r in recipients))
		self.assertTrue(any("relieving" in s.lower() for s in subjects))

		# overlapping application is refused, and so is using the busy reliever
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Leave Application", "staff_member": self.teacher, "leave_type": "Compassionate Leave",
							"from_date": add_days(start, 1), "to_date": add_days(start, 2), "reason": "x"}).insert()
		with self.assertRaises(frappe.ValidationError):
			# Jane is on leave that day, so she cannot relieve anyone
			frappe.get_doc({"doctype": "Leave Application", "staff_member": self.driver, "leave_type": "Annual Leave",
							"from_date": start, "to_date": start, "reason": "x", "reliever": self.teacher}).insert()
		la.cancel()
		self.assertEqual(frappe.db.get_value("Leave Application", la.name, "status"), "Cancelled")

	def test_leave_balance_and_gender_rules(self):
		start = add_days(next_monday(), 21)
		with self.assertRaises(frappe.ValidationError):  # 35 working days > 21 entitled
			frappe.get_doc({"doctype": "Leave Application", "staff_member": self.teacher, "leave_type": "Annual Leave",
							"from_date": start, "to_date": add_days(start, 48), "reason": "x", "reliever": self.reliever}).insert()
		with self.assertRaises(frappe.ValidationError):  # paternity is for male staff
			frappe.get_doc({"doctype": "Leave Application", "staff_member": self.teacher, "leave_type": "Paternity Leave",
							"from_date": start, "to_date": start, "reason": "x"}).insert()

	# ------------------------------------------------------------------ expenses
	def test_expense_two_level_approval_posts_journal_entry(self):
		from school_erp.api.expenses import decide, request_approval

		cat = frappe.get_all("Expense Category", limit=1, pluck="name")[0]
		big = frappe.get_doc({"doctype": "School Expense", "expense_category": cat, "amount": 25000, "payee": "Fundi Ltd",
							  "mode_of_payment": "_Test School Cash", "description": "Roof repair"}).insert()
		self.assertEqual(big.status, "Draft")
		self.assertEqual(request_approval(big.name), "Pending Approval")
		self.assertEqual(frappe.db.get_value("School Expense", big.name, "levels_required"), 2)
		self.assertEqual(decide(big.name, "Approved"), "Pending Final Approval")
		self.assertEqual(decide(big.name, "Approved"), "Approved")
		big.reload()
		self.assertEqual(big.docstatus, 1)
		je = frappe.get_doc("Journal Entry", big.journal_entry)
		self.assertEqual(je.docstatus, 1)
		self.assertEqual(flt(je.total_debit), 25000)

		small = frappe.get_doc({"doctype": "School Expense", "expense_category": cat, "amount": 4000, "payee": "Shop",
								"mode_of_payment": "_Test School Cash", "description": "Chalk"}).insert()
		request_approval(small.name)
		self.assertEqual(decide(small.name, "Approved"), "Approved")  # one approval is enough under the limit

		rej = frappe.get_doc({"doctype": "School Expense", "expense_category": cat, "amount": 500, "payee": "X",
							  "mode_of_payment": "_Test School Cash", "description": "?"}).insert()
		request_approval(rej.name)
		with self.assertRaises(frappe.ValidationError):
			decide(rej.name, "Rejected")  # reason required
		self.assertEqual(decide(rej.name, "Rejected", "No receipt"), "Rejected")
		self.assertFalse(frappe.db.get_value("School Expense", rej.name, "journal_entry"))

		big.reload()
		big.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", je.name, "docstatus"), 2)

	# ------------------------------------------------------------------ driver logs
	def test_driver_check_in_alerts_on_failed_checks(self):
		if not frappe.db.exists("School Vehicle", "KTEST 001A"):
			frappe.get_doc({"doctype": "School Vehicle", "registration_number": "KTEST 001A", "default_driver": self.driver}).insert()
		frappe.db.set_single_value("School Settings", "transport_manager_user", "Administrator")
		frappe.db.delete("Driver Daily Log", {"driver": self.driver})
		log = frappe.get_doc({"doctype": "Driver Daily Log", "driver": self.driver, "vehicle": "KTEST 001A",
							  "odometer_start": 1000, "fuel_level": "Half", "fit_to_drive": 0}).insert()
		self.assertEqual(len(log.checklist), 12)  # default safety checklist filled in
		with self.assertRaises(frappe.ValidationError):
			log.submit()  # must declare fit to drive
		log.reload()
		log.fit_to_drive = 1
		for row in log.checklist:
			row.ok = 1
		log.checklist[1].ok = 0  # brakes
		log.checklist[1].remarks = "soft pedal"
		log.save()
		with patch(NOTIFY) as sent:
			log.submit()
		self.assertTrue(log.has_issues)
		self.assertTrue(any("Vehicle check issues" in c.args[1]["subject"] for c in sent.call_args_list))
		self.assertEqual(flt(frappe.db.get_value("School Vehicle", "KTEST 001A", "last_odometer")), 1000)
		log.odometer_end = 1042
		log.save()
		self.assertEqual(flt(frappe.db.get_value("Driver Daily Log", log.name, "distance_km")), 42)
		with self.assertRaises(frappe.ValidationError):  # one morning check-in per day
			frappe.get_doc({"doctype": "Driver Daily Log", "driver": self.driver, "vehicle": "KTEST 001A",
							"odometer_start": 1042, "fuel_level": "Half"}).insert()

	# ------------------------------------------------------------------ duty
	def test_duty_report_once_per_day(self):
		frappe.get_doc({"doctype": "Duty Roster", "from_date": nowdate(), "to_date": add_days(nowdate(), 6),
						"members": [{"staff_member": self.reliever, "duty_role": "Teacher on Duty"}]}).insert()
		frappe.db.delete("Duty Report", {"staff_member": self.reliever})
		r = frappe.get_doc({"doctype": "Duty Report", "staff_member": self.reliever, "general_remarks": "Calm day",
							"incidents": "Minor scuffle at break"}).insert()
		with patch(NOTIFY) as sent:
			r.submit()
		self.assertTrue(any("incidents reported" in c.args[1]["subject"] for c in sent.call_args_list))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Duty Report", "staff_member": self.reliever, "general_remarks": "again"}).insert()

	# ------------------------------------------------------------------ welfare
	def test_guest_complaint_is_sanitised_and_trackable(self):
		from school_erp.api.welfare import complaint_status

		frappe.db.set_single_value("School Settings", "complaint_daily_limit", 2)
		frappe.db.delete("Complaint", {"phone": ("like", "%799111222")})
		frappe.set_user("Guest")
		frappe.flags.in_web_form = True
		try:
			c = frappe.get_doc({"doctype": "Complaint", "complainant_name": "Mary Parent", "phone": "0799111222",
								"category": "Transport", "subject": "Bus late", "description": "Bus was 40 minutes late",
								"status": "Resolved", "priority": "Urgent", "assigned_to": "Administrator"})
			c.insert(ignore_permissions=True)
			frappe.get_doc({"doctype": "Complaint", "complainant_name": "Mary Parent", "phone": "0799111222", "category": "Meals",
							"subject": "b", "description": "b"}).insert(ignore_permissions=True)
			with self.assertRaises(frappe.ValidationError):  # daily limit per phone
				frappe.get_doc({"doctype": "Complaint", "complainant_name": "Mary", "phone": "+254799111222", "category": "Other",
								"subject": "c", "description": "c"}).insert(ignore_permissions=True)
		finally:
			frappe.flags.in_web_form = False
			frappe.set_user("Administrator")
		c.reload()
		self.assertEqual((c.status, c.source, c.priority, c.assigned_to), ("Open", "Web Form", "Medium", None))
		self.assertTrue(complaint_status(c.name, "+254 799 111 222")["found"])
		self.assertFalse(complaint_status(c.name, "0700000000")["found"])
		c.status = "Resolved"
		with self.assertRaises(frappe.ValidationError):
			c.save()  # resolution text required
		c.reload()
		c.status = "Resolved"
		c.resolution = "Driver warned; route timing changed"
		c.save()
		self.assertTrue(c.resolved_on)

	def test_discipline_incident(self):
		student = frappe.get_all("Student", limit=1, pluck="name")
		if not student:
			from school_erp.tests.test_integration import TestSchoolFlow

			student = [TestSchoolFlow.make_student(self, takes_lunch=0, transport_route=None).name]
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Discipline Incident", "student": student[0], "category": "Fighting",
							"description": "x", "action_taken": "Suspension"}).insert()
		with patch(NOTIFY) as sent:
			frappe.get_doc({"doctype": "Discipline Incident", "student": student[0], "category": "Bullying", "severity": "Major",
							"description": "Took lunch money"}).insert()
		self.assertTrue(any("Major discipline incident" in c.args[1]["subject"] for c in sent.call_args_list))

	# ------------------------------------------------------------------ fees per class per term
	def test_copy_fee_structures_to_next_term(self):
		from school_erp.api.billing import copy_fee_structures

		year = frappe.db.get_value("School Term", self.term, "school_year")
		target = frappe.db.get_value("School Term", {"school_year": year, "name": ("!=", self.term)}, "name")
		frappe.db.delete("School Fee Structure", {"school_term": target})
		out = copy_fee_structures(self.term, target, 10, 50)
		self.assertTrue(out["created"])
		new = frappe.get_doc("School Fee Structure", out["created"][0])
		tuition = next(r.amount for r in new.items if r.fee_type == "Tuition")
		self.assertEqual(flt(tuition), 27500)  # 25,000 + 10%, rounded to 50

	# ------------------------------------------------------------------ licensing
	def test_operations_need_license(self):
		try:
			set_license([m for m in ALL_MODULES if m not in ("staff", "expenses")])
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Leave Type", "leave_type_name": "_Blocked", "days_per_year": 1}).insert()
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Expense Category", "category_name": "_Blocked",
								"expense_account": frappe.get_all("Account", {"root_type": "Expense", "is_group": 0}, pluck="name", limit=1)[0]}).insert()
		finally:
			set_license(ALL_MODULES)

	# ------------------------------------------------------------------ every report runs
	def test_all_reports_run(self):
		from frappe.desk.query_report import run

		folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "school", "report")
		for slug in sorted(os.listdir(folder)):
			if not os.path.isdir(os.path.join(folder, slug)) or slug.startswith("_"):
				continue
			name = frappe.db.get_value("Report", {"name": ("like", slug.replace("_", "%"))}, "name") or slug
			mod = importlib.import_module(f"school_erp.school.report.{slug}.{slug}")
			filters = {"from_date": add_days(nowdate(), -60), "to_date": nowdate(), "status": "Active"}
			result = mod.execute(filters)
			self.assertIsNotNone(result, slug)
			self.assertTrue(frappe.db.exists("Report", name), f"Report record missing for {slug}")
			run(name, filters=filters)  # through Frappe's own runner (permissions, formatting)
