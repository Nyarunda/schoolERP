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

	# ------------------------------------------------------------------ dashboards & notices
	def test_notice_reaches_audience_and_can_be_acknowledged(self):
		from school_erp.school.doctype.school_notice.school_notice import acknowledge

		with patch(NOTIFY) as sent:
			n = frappe.get_doc({"doctype": "School Notice", "title": "Staff meeting", "audience": "Teaching Staff",
								"priority": "Important", "message": "<p>Friday 3:30 pm</p>"}).insert()
		users = sent.call_args.args[0]
		self.assertIn("jane.teacher@test.school", users)
		self.assertNotIn("dan.driver@test.school", users)  # drivers are not teaching staff
		n.reload()
		self.assertTrue(n.notified)
		self.assertGreaterEqual(n.audience_count, 2)
		self.assertTrue(n.expiry_date)
		frappe.set_user("jane.teacher@test.school")
		try:
			self.assertEqual(acknowledge(n.name), 1)
			self.assertEqual(acknowledge(n.name), 1)  # only counted once
		finally:
			frappe.set_user("Administrator")

	def test_management_dashboard_data(self):
		from school_erp.api.dashboard import management

		d = management()
		for key in ("students", "fees", "staff", "transport", "welfare", "expenses", "cashflow", "attention", "notices"):
			self.assertIn(key, d, key)
		self.assertEqual(len(d["fees"]["daily"]["values"]), 29)
		self.assertEqual(len(d["cashflow"]["labels"]), 6)
		frappe.set_user("dan.driver@test.school")
		try:
			with self.assertRaises(frappe.PermissionError):
				management()  # drivers don't see the management dashboard
		finally:
			frappe.set_user("Administrator")

	def test_staff_room_for_teacher(self):
		from school_erp.api.dashboard import staff_room

		frappe.set_user("jane.teacher@test.school")
		try:
			d = staff_room()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(d["staff"], self.teacher)
		self.assertTrue(d["greeting"].endswith("Jane"))
		leave_types = {b["leave_type"] for b in d["leave"]}
		self.assertIn("Maternity Leave", leave_types)
		self.assertNotIn("Paternity Leave", leave_types)  # Jane is female
		self.assertTrue(any(a["label"] == "Apply for leave" for a in d["actions"]))

	# ------------------------------------------------------------------ term billing runs
	def _fresh_students(self, n, **kw):
		from school_erp.tests.test_integration import TestSchoolFlow

		return [TestSchoolFlow.make_student(self, **kw).name for _i in range(n)]

	def test_billing_run_review_untick_and_post(self):
		frappe.db.set_single_value("School Settings", "notify_after_billing", 0)
		a, b, c = self._fresh_students(3)
		run = frappe.get_doc({"doctype": "Fee Billing Run", "school_term": self.term, "posting_date": nowdate(),
							  "due_date": add_days(nowdate(), 14), "classes": [{"school_class": "Grade 4"}],
							  "send_notifications": 0}).insert()
		run.get_students()
		rows = {r.student: r for r in run.students}
		for s in (a, b, c):
			self.assertIn(s, rows)
			self.assertEqual(flt(rows[s].total), 40000)
			self.assertIn("Tuition 25,000", rows[s].fee_lines)
		rows[c].include = 0  # leave one student out
		run.save()
		self.assertEqual(run.total_students, len(run.students) - 1)
		tuition = next(r for r in run.fee_summary if r.fee_type == "Tuition")
		self.assertEqual(tuition.students, run.total_students)
		run.submit()  # runs synchronously in tests
		run.reload()
		self.assertIn(run.status, ("Completed", "Completed with Errors"))
		rows = {r.student: r for r in run.students}
		self.assertEqual(rows[a].status, "Invoiced")
		self.assertEqual(frappe.db.get_value("Sales Invoice", rows[a].sales_invoice, "docstatus"), 1)
		self.assertEqual(rows[c].status, "Pending")  # unticked: not invoiced
		self.assertFalse(frappe.db.exists("Sales Invoice", {"student": c, "school_term": self.term}))
		self.assertEqual(flt(run.total_billed), sum(flt(r.total) for r in run.students if r.status == "Invoiced"))

		# a second run for the same term skips everyone already invoiced
		run2 = frappe.get_doc({"doctype": "Fee Billing Run", "school_term": self.term, "posting_date": nowdate(),
							   "due_date": add_days(nowdate(), 14), "classes": [{"school_class": "Grade 4"}]}).insert()
		run2.get_students()
		self.assertNotIn(a, [r.student for r in run2.students])
		self.assertIn(c, [r.student for r in run2.students])
		self.assertGreaterEqual(run2.already_billed, 2)

	def test_automatic_term_billing(self):
		from school_erp.api.billing import auto_bill_terms

		# a term starting today, with its own fee structure
		year = frappe.db.get_value("School Term", self.term, "school_year")
		label = "Auto Term " + frappe.generate_hash(length=5)  # a fresh term each run
		tname = frappe.get_doc({"doctype": "School Term", "term_name": label, "school_year": year,
								"start_date": nowdate(), "end_date": add_days(nowdate(), 60)}).insert().name
		frappe.db.set_single_value("School Settings", "auto_bill_warned_on", None)
		settings = frappe.get_doc("School Settings")
		settings.update({"auto_bill_terms": 1, "auto_bill_mode": "Create draft for review", "auto_bill_days_before": 0,
						 "auto_bill_due_days": 10, "auto_bill_notify_parents": 0})
		settings.save()
		try:
			with patch(NOTIFY) as sent:
				auto_bill_terms()  # no fee structure yet: bursar is told, nothing created
			self.assertFalse(frappe.db.exists("Fee Billing Run", {"school_term": tname}))
			self.assertTrue(any("waiting for a fee structure" in c.args[1]["subject"] for c in sent.call_args_list))

			frappe.get_doc({"doctype": "School Fee Structure", "school_term": tname, "school_class": "Grade 4", "boarding_type": "All",
							"items": [{"fee_type": "Tuition", "amount": 20000}]}).insert()
			with patch(NOTIFY) as sent:
				auto_bill_terms()
			runs = frappe.get_all("Fee Billing Run", filters={"school_term": tname}, fields=["name", "docstatus", "auto_generated", "total_students", "due_date"])
			self.assertEqual(len(runs), 1)
			self.assertEqual((runs[0].docstatus, runs[0].auto_generated), (0, 1))  # draft for review
			self.assertGreater(runs[0].total_students, 0)
			self.assertEqual(getdate(runs[0].due_date), getdate(add_days(nowdate(), 10)))
			self.assertTrue(any("ready for review" in c.args[1]["subject"] for c in sent.call_args_list))
			auto_bill_terms()  # never twice for the same term
			self.assertEqual(frappe.db.count("Fee Billing Run", {"school_term": tname}), 1)

			# "Post automatically" posts straight away
			frappe.delete_doc("Fee Billing Run", runs[0].name)
			settings.reload()
			settings.auto_bill_mode = "Post automatically"
			settings.save()
			auto_bill_terms()
			run = frappe.get_doc("Fee Billing Run", {"school_term": tname})
			self.assertEqual(run.docstatus, 1)
			self.assertTrue(frappe.db.exists("Sales Invoice", {"school_term": tname, "docstatus": 1}))
		finally:
			frappe.db.set_single_value("School Settings", "auto_bill_terms", 0)

	# ------------------------------------------------------------------ Frappe Workflow approvals
	def test_workflows_installed(self):
		for name, dt in (("School Leave Approval", "Leave Application"), ("School Expense Approval", "School Expense")):
			wf = frappe.get_doc("Workflow", name)
			self.assertEqual((wf.document_type, wf.is_active, wf.workflow_state_field), (dt, 1, "status"))
		self.assertTrue(frappe.db.exists("Workflow State", "Pending Final Approval"))

	def test_leave_workflow_only_own_approver_and_toasts(self):
		from frappe.model.workflow import apply_workflow

		frappe.db.set_value("Staff Member", self.teacher, "reports_to", self.reliever)
		frappe.get_doc("Staff Member", self.teacher).save()  # grants Ruth the Leave Approver role
		ruth = frappe.db.get_value("Staff Member", self.reliever, "user")
		dan = frappe.db.get_value("Staff Member", self.driver, "user")
		jane = frappe.db.get_value("Staff Member", self.teacher, "user")
		self.assertIn("Leave Approver", frappe.get_roles(ruth))
		start = add_days(next_monday(), 35)
		la = frappe.get_doc({"doctype": "Leave Application", "staff_member": self.teacher, "leave_type": "Compassionate Leave",
							 "from_date": start, "to_date": start, "reason": "Funeral"}).insert()
		self.assertEqual(la.approver, ruth)
		try:
			frappe.set_user(dan)  # not the approver
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
				apply_workflow(frappe.get_doc("Leave Application", la.name), "Approve")
			frappe.set_user(ruth)
			doc = frappe.get_doc("Leave Application", la.name)
			doc.decision_comment = None
			with self.assertRaises(frappe.ValidationError):  # rejecting needs a reason
				apply_workflow(doc, "Reject")
			with patch("frappe.publish_realtime") as rt, patch(NOTIFY):
				done = apply_workflow(frappe.get_doc("Leave Application", la.name), "Approve")
			self.assertEqual((done.status, done.docstatus, done.approved_by), ("Approved", 1, ruth))
			toasts = [c for c in rt.call_args_list if c.args and c.args[0] == "school_toast"]
			self.assertTrue(any(c.kwargs.get("user") == jane and c.args[1]["indicator"] == "green" for c in toasts))
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Staff Member", self.teacher, "reports_to", None)

	def test_expense_workflow_no_self_approval(self):
		from frappe.model.workflow import apply_workflow

		email = "bursar.test@test.school"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Bursar", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.get_doc("User", email).add_roles("Bursar", "Staff")
		cat = frappe.get_all("Expense Category", limit=1, pluck="name")[0]
		try:
			frappe.set_user(email)
			e = frappe.get_doc({"doctype": "School Expense", "expense_category": cat, "amount": 3000, "payee": "Shop",
								"mode_of_payment": "_Test School Cash", "description": "Markers"}).insert()
			self.assertEqual(e.status, "Draft")
			e = apply_workflow(e, "Send for Approval")
			self.assertEqual(e.status, "Pending Approval")
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
				apply_workflow(frappe.get_doc("School Expense", e.name), "Approve")  # own expense
		finally:
			frappe.set_user("Administrator")
		with patch("frappe.publish_realtime") as rt, patch(NOTIFY):
			done = apply_workflow(frappe.get_doc("School Expense", e.name), "Approve")
		self.assertEqual((done.status, done.docstatus), ("Approved", 1))
		self.assertTrue(done.journal_entry)
		self.assertTrue(any(c.args[0] == "school_toast" and c.kwargs.get("user") == email for c in rt.call_args_list if c.args))
