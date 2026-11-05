"""Class attendance (registers, absence SMS, summaries) and marks approval (Head of Department workflow)."""

from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, getdate, nowdate

from school_erp.tests.test_integration import TestCase, setup_school

NOTIFY = "frappe.desk.doctype.notification_log.notification_log.enqueue_create_notification"
SMS = "school_erp.api.messaging.send_sms"


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0].title(),
						"send_welcome_email": 0}).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(*roles)
	return email


def _toasts(rt, user):
	return [c.args[1] for c in rt.call_args_list if c.args and c.args[0] == "school_toast" and c.kwargs.get("user") == user]


class TestAttendanceAndMarks(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		from school_erp.api.setup import run_setup

		run_setup()
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_stream(self, cls="Grade 5"):
		name = "Att" + frappe.generate_hash(length=5)
		frappe.get_doc({"doctype": "Stream", "school_class": cls, "stream_name": name}).insert()
		return f"{cls} {name}"

	def make_students(self, stream, names):
		return [frappe.get_doc({
			"doctype": "Student", "first_name": n, "last_name": "Test", "stream": stream, "gender": "Female",
			"guardians": [{"guardian_name": "Mama " + n, "relation": "Mother", "mobile_no": "0712345678", "is_primary": 1}],
		}).insert().name for n in names]

	# ================================================================= attendance
	def test_register_saves_once_per_day_with_counts(self):
		from school_erp.api.attendance import register, save_register

		stream = self.make_stream()
		a, b, c, d = self.make_students(stream, ["Asha", "Baraka", "Chebet", "Daudi"])
		first = register(stream)
		self.assertEqual([s["status"] for s in first["students"]], ["Present"] * 4)  # everyone starts present
		self.assertFalse(first["saved"])
		r = save_register(stream, nowdate(), [{"student": a, "status": "Absent", "note": "sick"}, {"student": b, "status": "Late"},
											  {"student": c, "status": "Excused"}, {"student": d, "status": "Present"}])
		self.assertEqual((r["present"], r["late"], r["absent"], r["excused"], r["percent"]), (1, 1, 1, 1, 50.0))
		again = save_register(stream, nowdate(), [{"student": x, "status": "Present"} for x in (a, b, c, d)])
		self.assertEqual(again["name"], r["name"])  # same register, updated
		self.assertEqual(frappe.db.count("Class Attendance", {"stream": stream}), 1)
		self.assertEqual(register(stream)["saved"]["name"], r["name"])
		with self.assertRaises(frappe.ValidationError):  # a second register for the same day
			frappe.get_doc({"doctype": "Class Attendance", "stream": stream, "attendance_date": nowdate(),
							"students": [{"student": a}]}).insert()
		with self.assertRaises(frappe.ValidationError):  # the future
			save_register(stream, add_days(nowdate(), 1), [{"student": a, "status": "Present"}])

	def test_parents_get_one_sms_per_absence(self):
		from school_erp.api.attendance import save_register

		frappe.db.set_single_value("School Settings", {"attendance_sms_absent": 1,
			"attendance_absent_sms": "{first_name} was absent on {date}. {school_name}"})
		self.addCleanup(frappe.db.set_single_value, "School Settings", "attendance_sms_absent", 0)
		stream = self.make_stream()
		a, b = self.make_students(stream, ["Akinyi", "Brian"])
		with patch(SMS, return_value={"sent": ["254712345678"], "failed": []}) as sms:
			r = save_register(stream, nowdate(), [{"student": a, "status": "Absent"}, {"student": b, "status": "Present"}])
			self.assertEqual(r["notified"], 1)
			self.assertEqual(sms.call_count, 1)
			self.assertIn("Akinyi was absent", sms.call_args.args[1])
			save_register(stream, nowdate(), [{"student": a, "status": "Absent"}, {"student": b, "status": "Present"}])
			self.assertEqual(sms.call_count, 1)  # still absent: not told twice
			save_register(stream, nowdate(), [{"student": a, "status": "Absent"}, {"student": b, "status": "Absent"}])
			self.assertEqual(sms.call_count, 2)  # Brian now absent too
		self.assertTrue(frappe.db.get_value("Class Attendance Student", {"student": a}, "parent_notified"))
		# a register filled in for an earlier day never texts parents
		with patch(SMS, return_value={"sent": ["x"], "failed": []}) as sms:
			save_register(stream, add_days(nowdate(), -1), [{"student": a, "status": "Absent"}, {"student": b, "status": "Absent"}])
			sms.assert_not_called()

	def test_teacher_can_only_change_todays_register(self):
		from school_erp.api.attendance import save_register

		stream = self.make_stream()
		(a,) = self.make_students(stream, ["Imani"])
		save_register(stream, add_days(nowdate(), -2), [{"student": a, "status": "Absent"}])  # the Head Teacher back-fills
		teacher = _user("register.teacher@test.school", "Teacher")
		frappe.db.set_single_value("School Settings", "attendance_edit_days", 0)
		frappe.set_user(teacher)
		save_register(stream, nowdate(), [{"student": a, "status": "Present"}])
		with self.assertRaises(frappe.PermissionError):
			save_register(stream, add_days(nowdate(), -2), [{"student": a, "status": "Present"}])
		frappe.set_user("Administrator")
		frappe.db.set_single_value("School Settings", "attendance_edit_days", 3)
		self.addCleanup(frappe.db.set_single_value, "School Settings", "attendance_edit_days", 0)
		frappe.set_user(teacher)
		save_register(stream, add_days(nowdate(), -2), [{"student": a, "status": "Present"}])  # inside the window now

	def test_summaries_for_dashboard_portal_and_reports(self):
		from school_erp.api.attendance import day_summary, save_register, student_attendance

		stream = self.make_stream()
		a, b = self.make_students(stream, ["Wanjiku", "Otieno"])
		other = self.make_stream()
		self.make_students(other, ["Zawadi"])
		for i, (sa, sb) in enumerate([("Present", "Absent"), ("Late", "Present"), ("Absent", "Present"), ("Present", "Present")]):
			save_register(stream, add_days(nowdate(), -i), [{"student": a, "status": sa}, {"student": b, "status": sb}])
		mine = student_attendance(a)
		self.assertEqual((mine["marked"], mine["attended"], mine["absent"], mine["percent"]), (4, 3, 1, 75.0))
		self.assertEqual(len(mine["recent_absences"]), 1)
		today = {r["stream"]: r for r in day_summary()["streams"]}
		self.assertTrue(today[stream]["taken"])
		self.assertFalse(today[other]["taken"])  # shows up as missing on the dashboard
		self.assertEqual(today[stream]["absent"], 1)

		from school_erp.school.report.attendance_register.attendance_register import execute

		cols, data, *_ = execute({"from_date": add_days(nowdate(), -5), "to_date": nowdate(), "stream": stream})
		self.assertEqual({r.student: r["percent"] for r in data}, {a: 75.0, b: 75.0})
		cols, data, *_ = execute({"from_date": add_days(nowdate(), -5), "to_date": nowdate(), "stream": stream, "below": 80})
		self.assertEqual(len(data), 2)

		from school_erp.api.portal import child_summary

		portal = child_summary(a)["attendance"]  # this term's registers, for the parent portal
		if portal:
			self.assertLessEqual(portal["marked"], 4)
			self.assertIn("percent", portal)

	# ================================================================= marks approval
	def _exam_with_sheet(self, subject, owner):
		stream = self.make_stream("Grade 6")
		studs = self.make_students(stream, ["Neema", "Tumaini"])
		exam = frappe.get_doc({"doctype": "Exam", "exam_name": "Approval " + frappe.generate_hash(length=4), "school_term": self.term,
							   "grading_scale": "CBC", "max_marks": 100, "classes": [{"school_class": "Grade 6"}],
							   "subjects": [{"subject": subject}]}).insert()
		frappe.set_user(owner)
		ms = frappe.get_doc({"doctype": "Exam Mark Sheet", "exam": exam.name, "stream": stream, "subject": subject})
		ms.get_students()
		for m, v in zip(ms.marks, ("78", "64")):
			m.marks = v
		ms.insert()
		frappe.set_user("Administrator")
		return exam, ms, studs

	def _subject_with_hod(self, hod):
		name = "Science " + frappe.generate_hash(length=4)
		frappe.get_doc({"doctype": "Subject", "subject_name": name, "head_of_department": hod}).insert()
		return name

	def test_head_of_department_approves_or_returns_marks(self):
		hod = _user("hod.science@test.school", "Teacher")
		teacher = _user("science.teacher@test.school", "Teacher")
		other_hod = _user("hod.languages@test.school", "Teacher", "Head of Department")
		subject = self._subject_with_hod(hod)
		self.assertIn("Head of Department", frappe.get_roles(hod))  # given automatically
		exam, ms, _ = self._exam_with_sheet(subject, teacher)
		self.assertEqual((ms.approval_status, ms.reviewer), ("Draft", hod))

		frappe.set_user(teacher)
		with self.assertRaises(frappe.PermissionError):  # a plain Submit skips the Head of Department
			frappe.get_doc("Exam Mark Sheet", ms.name).submit()
		frappe.set_user(teacher)
		with patch("frappe.publish_realtime") as rt, patch(NOTIFY):
			ms = apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Send for Approval")
		self.assertEqual(ms.approval_status, "Pending Approval")
		self.assertTrue(_toasts(rt, hod))  # the approver is told
		with self.assertRaises(frappe.ValidationError):  # the teacher can't approve their own marks
			apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Approve")

		frappe.set_user(other_hod)  # a Head of Department, but not for this subject
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Approve")

		frappe.set_user(hod)
		with self.assertRaises(frappe.ValidationError):  # returning needs a reason
			apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Return")
		from school_erp.setup.workflows import save_rejection_reason

		save_rejection_reason("Exam Mark Sheet", ms.name, "Tumaini's mark looks too low, check the script")
		with patch("frappe.publish_realtime") as rt, patch(NOTIFY):
			ms = apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Return")
		self.assertEqual((ms.approval_status, ms.docstatus), ("Returned", 0))
		toast = _toasts(rt, teacher)
		self.assertTrue(toast and toast[0]["indicator"] == "red" and "too low" in toast[0]["message"])

		frappe.set_user(teacher)
		ms = frappe.get_doc("Exam Mark Sheet", ms.name)
		ms.marks[1].marks = "68"
		ms.save()
		ms = apply_workflow(ms, "Resend")
		self.assertEqual((ms.approval_status, ms.review_comment), ("Pending Approval", None))

		frappe.set_user(hod)
		with patch("frappe.publish_realtime") as rt, patch(NOTIFY):
			ms = apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Approve")
		self.assertEqual((ms.approval_status, ms.docstatus, ms.approved_by), ("Approved", 1, hod))
		self.assertEqual(_toasts(rt, teacher)[0]["indicator"], "green")

	def test_report_cards_use_approved_marks_and_bulk_approval(self):
		from school_erp.api.exams import approval_queue, approval_queue_names, approve_sheets, exam_progress, generate_report_cards

		hod = _user("hod.maths@test.school", "Teacher")
		teacher = _user("maths.teacher@test.school", "Teacher")
		subject = self._subject_with_hod(hod)
		exam, ms, studs = self._exam_with_sheet(subject, teacher)
		frappe.set_user(teacher)
		with patch(NOTIFY):
			apply_workflow(frappe.get_doc("Exam Mark Sheet", ms.name), "Send for Approval")
		frappe.set_user("Administrator")
		mine = [c["state"] for r in exam_progress(exam.name)["rows"] if r["stream"] == ms.stream for c in r["cells"]]
		self.assertEqual(mine, ["pending"])
		with self.assertRaises(frappe.ValidationError):  # nothing approved yet
			generate_report_cards(exam.name)

		frappe.set_user(teacher)
		self.assertEqual(approval_queue_names(exam.name), [])  # teachers have no approval queue
		self.assertEqual(approve_sheets([ms.name])["approved"], 0)
		frappe.set_user(hod)
		groups = approval_queue(exam.name)
		self.assertEqual([s.name for g in groups for s in g["sheets"]], [ms.name])
		with patch(NOTIFY):
			self.assertEqual(approve_sheets([ms.name]), {"approved": 1, "failed": []})
		frappe.set_user("Administrator")
		self.assertEqual(exam_progress(exam.name)["done"], 1)
		res = generate_report_cards(exam.name)
		self.assertEqual((res["report_cards"], res["not_included"]), (2, 0))

	def test_approval_can_be_switched_off(self):
		frappe.db.set_single_value("School Settings", "marks_need_approval", 0)
		from school_erp.setup.workflows import make_workflows

		make_workflows()
		try:
			teacher = _user("quick.teacher@test.school", "Teacher")
			exam, ms, _ = self._exam_with_sheet(self._subject_with_hod(None), teacher)
			frappe.set_user(teacher)
			ms = frappe.get_doc("Exam Mark Sheet", ms.name)
			ms.submit()  # straight to submitted, as before
			self.assertEqual((ms.docstatus, ms.approval_status), (1, "Approved"))
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("School Settings", "marks_need_approval", 1)
			make_workflows()
