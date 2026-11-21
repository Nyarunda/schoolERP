"""Graduate a learner, move learners between classes, move a learner back from a promotion
(specs/features/students-sidebar-and-class-moves). bench --site <site> run-tests --module school_erp.tests.test_class_moves"""

from unittest.mock import patch

import frappe
from frappe.utils import getdate, nowdate

from school_erp.api import students as api
from school_erp.tests.test_integration import TestCase, setup_school


class TestClassMoves(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.set_user("Administrator")
		tag = frappe.generate_hash(length=4).upper()
		cls.g4, cls.g5 = cls._stream("Grade 4", f"Mv{tag}"), cls._stream("Grade 5", f"Mv{tag}")
		cls.g4b = cls._stream("Grade 4", f"Mw{tag}")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._pub.stop()
		super().tearDownClass()

	@staticmethod
	def _stream(cls_name, suffix):
		name = f"{cls_name} {suffix}"
		if not frappe.db.exists("Stream", name):
			frappe.get_doc({"doctype": "Stream", "school_class": cls_name, "stream_name": suffix}).insert()
		return name

	def setUp(self):
		frappe.set_user("Administrator")

	def kid(self, stream, first="Mover"):
		return frappe.get_doc({"doctype": "Student", "first_name": first, "last_name": "Class", "stream": stream,
							   "gender": "Male", "guardians": [{"guardian_name": "Baba", "relation": "Father",
																"mobile_no": "0712000999", "is_primary": 1}]}).insert().name

	def comments(self, student):
		return frappe.get_all("Comment", filters={"reference_doctype": "Student", "reference_name": student,
												  "comment_type": "Info"}, pluck="content")

	def test_graduate_and_readmit(self):
		s = self.kid(self.g5)
		api.graduate(s, note="Completed Grade 9")
		doc = frappe.get_doc("Student", s)
		self.assertEqual((doc.status, getdate(doc.leaving_date), doc.leaving_reason),
						 ("Graduated", getdate(nowdate()), "Completed Grade 9"))
		with self.assertRaises(frappe.ValidationError):
			api.graduate(s)  # already graduated
		with self.assertRaises(frappe.ValidationError):
			api.move_class(s, self.g4, "Repeating the class")  # left the school: re-admit first
		doc.status = "Active"
		doc.save()
		self.assertFalse(frappe.db.get_value("Student", s, "leaving_date"))

	def test_move_class_back_records_why(self):
		s = self.kid(self.g5)
		out = api.move_class(s, self.g4, "Repeating the class", "Parents asked")
		self.assertEqual((out["kind"], out["from"], out["to"]), ("back", self.g5, self.g4))
		self.assertEqual(frappe.db.get_value("Student", s, ["stream", "school_class"]), (self.g4, "Grade 4"))
		note = self.comments(s)[0]
		for words in ("Moved back", self.g5, self.g4, "Repeating the class", "Parents asked"):
			self.assertIn(words, note)
		self.assertEqual(api.move_class(s, self.g4b, "Change of stream")["kind"], "same class")
		self.assertEqual(api.move_class(s, self.g5, "Moved up a class")["kind"], "up")
		with self.assertRaises(frappe.ValidationError):
			api.move_class(s, self.g5, "Moved up a class")  # already there
		with self.assertRaises(frappe.ValidationError):
			api.move_class(s, self.g4, "Because")  # not a reason

	def test_move_warns_about_invoice(self):
		from school_erp.api.billing import bill_single_student

		s = self.kid("Grade 4 Test")  # Grade 4 has a fee structure in setup_school
		bill_single_student(s, self.term)
		with patch("school_erp.school.doctype.school_term.school_term.get_current_term", return_value=self.term):
			out = api.move_class(s, self.g5, "Moved up a class")
		self.assertTrue(out["warning"])
		self.assertIn("Grade 4", out["warning"])

	def test_bulk_actions(self):
		a, b = self.kid(self.g5, "Alpha"), self.kid(self.g5, "Beta")
		out = api.bulk_move([a, b], self.g4, "Promoted by mistake")
		self.assertEqual((out["done"], out["failed"]), (2, []))
		self.assertEqual({frappe.db.get_value("Student", x, "stream") for x in (a, b)}, {self.g4})
		out = api.bulk_move(frappe.as_json([a, b]), self.g4, "Promoted by mistake")  # both already there
		self.assertEqual((out["done"], len(out["failed"])), (0, 2))
		out = api.bulk_graduate([a, b])
		self.assertEqual(out["done"], 2)
		self.assertEqual({frappe.db.get_value("Student", x, "status") for x in (a, b)}, {"Graduated"})

	def test_move_back_from_promotion(self):
		year = getdate(nowdate()).year
		for y in (year, year + 1):
			if not frappe.db.exists("School Year", str(y)):
				frappe.get_doc({"doctype": "School Year", "year_name": str(y), "start_date": f"{y}-01-01",
								"end_date": f"{y}-12-31"}).insert()
		s = self.kid(self.g4, "Promoted")
		p = frappe.get_doc({"doctype": "Student Promotion", "from_year": str(year), "to_year": str(year + 1),
							"classes": [{"school_class": "Grade 4"}], "make_to_year_current": 0, "create_streams": 1}).insert()
		p.get_students()
		for i in p.items:
			if i.student != s:
				i.action = "Repeat"  # leave other test learners alone
		p.save()
		p.submit()
		self.assertEqual(frappe.db.get_value("Student", s, "stream"), self.g5)
		self.assertIn(s, [r.student for r in api.promoted_students(p.name)])
		out = api.move_back_from_promotion(p.name, s)
		self.assertEqual((out["to"], out["kind"]), (self.g4, "back"))
		self.assertEqual(frappe.db.get_value("Student", s, "stream"), self.g4)
		self.assertEqual(frappe.db.get_value("Student Promotion Item", {"parent": p.name, "student": s}, "status"), "Moved back")
		self.assertNotIn(s, [r.student for r in api.promoted_students(p.name)])
		with self.assertRaises(frappe.ValidationError):
			api.move_back_from_promotion(p.name, s)  # only once

	def test_needs_write_permission(self):
		s = self.kid(self.g5)
		email = "readonly.mover@test.school"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Viewer", "send_welcome_email": 0,
							"roles": [{"role": "School Viewer"}]}).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			for call in (lambda: api.graduate(s), lambda: api.move_class(s, self.g4, "Repeating the class"),
						 lambda: api.bulk_move([s], self.g4, "Repeating the class"), lambda: api.bulk_graduate([s])):
				with self.assertRaises(frappe.PermissionError):
					call()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Student", s, ["stream", "status"]), (self.g5, "Active"))
