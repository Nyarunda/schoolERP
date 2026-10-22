"""End-to-end: year-end promotion, exams & report cards, parent portal & STK push."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from school_erp.tests.test_integration import TestCase, setup_school


def fake_response(payload, status=200):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = payload
	r.text = "x"
	r.headers = {"content-type": "application/json"}
	return r


class TestFeatures(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		from school_erp.api.setup import run_setup

		run_setup()  # grading scales, leave types...
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def make_stream(self, cls, name):
		full = f"{cls} {name}"
		if not frappe.db.exists("Stream", full):
			frappe.get_doc({"doctype": "Stream", "school_class": cls, "stream_name": name}).insert()
		return full

	def make_student(self, stream, first="Kid", **kw):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Test", "stream": stream, "gender": kw.pop("gender", "Female"),
			"guardians": [{"guardian_name": "Mama " + first, "relation": "Mother", "mobile_no": kw.pop("phone", "0712345678"),
						   "email": kw.pop("email", None), "is_primary": 1}],
			**kw,
		}).insert()

	# ------------------------------------------------------------------ promotion
	def test_year_end_promotion(self):
		year = getdate(nowdate()).year
		for y in (year, year + 1):
			if not frappe.db.exists("School Year", str(y)):
				frappe.get_doc({"doctype": "School Year", "year_name": str(y), "start_date": f"{y}-01-01", "end_date": f"{y}-12-31"}).insert()
		s_up = self.make_student(self.make_stream("Grade 7", "Promo"), "Up").name
		s_stay = self.make_student(self.make_stream("Grade 7", "Promo"), "Stay").name
		s_grad = self.make_student(self.make_stream("Grade 9", "Promo"), "Grad").name
		frappe.db.delete("Stream", {"name": "Grade 8 Promo"})

		p = frappe.get_doc({"doctype": "Student Promotion", "from_year": str(year), "to_year": str(year + 1),
							"classes": [{"school_class": "Grade 7"}, {"school_class": "Grade 9"}], "make_to_year_current": 0}).insert()
		p.get_students()
		mine = {s_up, s_stay, s_grad}
		for i in p.items:
			if i.student not in mine or i.student == s_stay:
				i.action = "Repeat"  # leave other test students alone
		p.save()
		items = {i.student: i for i in p.items}
		self.assertEqual((items[s_up].action, items[s_up].new_stream), ("Promote", "Grade 8 Promo"))
		self.assertEqual(items[s_grad].action, "Graduate")
		self.assertEqual(items[s_stay].new_stream, "Grade 7 Promo")
		self.assertEqual(p.to_graduate, 1)
		p.submit()
		self.assertEqual(frappe.db.get_value("Student", s_up, ["stream", "school_class"]), ("Grade 8 Promo", "Grade 8"))
		self.assertTrue(frappe.db.exists("Stream", "Grade 8 Promo"))  # created
		self.assertEqual(frappe.db.get_value("Student", s_stay, "stream"), "Grade 7 Promo")
		self.assertEqual(frappe.db.get_value("Student", s_grad, "status"), "Graduated")
		self.assertEqual(p.status, "Completed")

	# ------------------------------------------------------------------ exams
	def test_exam_marks_report_cards_and_positions(self):
		stream = self.make_stream("Grade 6", "Exam" + frappe.generate_hash(length=4))
		a, b, c = (self.make_student(stream, n).name for n in ("Alpha", "Bravo", "Charlie"))
		for sub in ("Mathematics", "English"):
			if not frappe.db.exists("Subject", sub):
				frappe.get_doc({"doctype": "Subject", "subject_name": sub}).insert()
		exam = frappe.get_doc({"doctype": "Exam", "exam_name": "End Term " + frappe.generate_hash(length=4), "school_term": self.term,
							   "grading_scale": "KCSE (8-4-4)", "max_marks": 100, "classes": [{"school_class": "Grade 6"}],
							   "subjects": [{"subject": "Mathematics"}, {"subject": "English"}]}).insert()
		marks = {"Mathematics": {a: "80", b: "60", c: "60"}, "English": {a: "70", b: "70", c: None}}
		for sub, row in marks.items():
			ms = frappe.get_doc({"doctype": "Exam Mark Sheet", "exam": exam.name, "stream": stream, "subject": sub})
			ms.get_students()
			for m in ms.marks:
				if m.student in row:
					if row[m.student] is None:
						m.absent = 1
					else:
						m.marks = row[m.student]
			ms.insert()
			if sub == "Mathematics":
				self.assertEqual(ms.average, round((80 + 60 + 60) / 3, 1))
				self.assertEqual({m.student: m.grade for m in ms.marks}, {a: "A", b: "B-", c: "B-"})
			ms.submit()
		with self.assertRaises(frappe.ValidationError):  # duplicate sheet
			frappe.get_doc({"doctype": "Exam Mark Sheet", "exam": exam.name, "stream": stream, "subject": "English",
							"marks": [{"student": a, "marks": "1"}]}).insert()
		bad = frappe.get_doc({"doctype": "Exam Mark Sheet", "exam": exam.name, "stream": stream, "subject": "Mathematics"})
		bad.append("marks", {"student": a, "marks": "120"})
		with self.assertRaises(frappe.ValidationError):  # over the maximum (and duplicate)
			bad.insert()

		from school_erp.api.exams import generate_report_cards, publish, report_card_pdf

		self.assertEqual(generate_report_cards(exam.name)["report_cards"], 3)
		rc = {r.student: r for r in frappe.get_all("Report Card", filters={"exam": exam.name},
												   fields=["name", "student", "mean_percent", "mean_grade", "stream_position", "stream_size"])}
		self.assertEqual((rc[a].mean_percent, rc[a].mean_grade, rc[a].stream_position), (75, "A-", 1))
		self.assertEqual((rc[b].mean_percent, rc[b].stream_position), (65, 2))
		self.assertEqual((rc[c].mean_percent, rc[c].stream_position), (60, 3))  # English absent: mean over Maths only
		self.assertEqual(rc[a].stream_size, 3)
		doc = frappe.get_doc("Report Card", rc[a].name)
		self.assertTrue(doc.class_teacher_remark)
		self.assertEqual({s.subject: s.subject_position for s in doc.subjects}, {"Mathematics": "1/3", "English": "1/2"})

		doc.head_teacher_remark = "Well done"
		doc.save()
		generate_report_cards(exam.name)  # regenerating keeps the remarks
		self.assertEqual(frappe.db.get_value("Report Card", rc[a].name, "head_teacher_remark"), "Well done")

		self.assertEqual(publish(exam.name, notify_parents=0)["published"], 3)
		self.assertEqual(frappe.db.get_value("Report Card", rc[a].name, "status"), "Published")
		self.assertTrue(report_card_pdf(rc[a].name).startswith(b"%PDF"))

	# ------------------------------------------------------------------ parent portal + STK push
	def test_parent_portal_and_stk_payment(self):
		from school_erp.api import portal, stk
		from school_erp.api.billing import bill_single_student
		from school_erp.api.payments import party_balance

		phone = "0798" + frappe.generate_hash(length=6)[:6].translate(str.maketrans("abcdef", "123456"))
		ck1, ck2 = "ws_CO_" + frappe.generate_hash(length=10), "ws_CO_" + frappe.generate_hash(length=10)
		stream = self.make_stream("Grade 4", "Portal")
		mine = self.make_student(stream, "Zawadi", phone=phone, takes_lunch=1)
		other = self.make_student(stream, "Other", phone="0700000001")
		bill_single_student(mine.name, self.term)
		out = portal.give_portal_access(student=mine.name, send_sms=0)
		self.assertEqual(out["new_logins"], 1)
		user = frappe.db.get_value("Student Guardian", {"parent": mine.name}, "user")
		self.assertTrue(user)
		self.assertIn("Parent", frappe.get_roles(user))
		self.assertEqual(frappe.db.get_value("User", user, "user_type"), "Website User")
		# parents can sign in with the number as they know it (07...) or in international form (2547...)
		self.assertEqual(frappe.db.get_value("User", user, ["mobile_no", "username"]), (phone, "254" + phone[1:]))
		from frappe.core.doctype.user.user import User

		self.assertEqual(User.find_by_credentials(phone, "x", validate_password=False)["name"], user)
		self.assertEqual(User.find_by_credentials("254" + phone[1:], "x", validate_password=False)["name"], user)
		self.assertEqual(portal.give_portal_access(student=mine.name, send_sms=0)["new_logins"], 0)  # idempotent

		frappe.get_doc({"doctype": "School Notice", "title": "Sports day Friday", "audience": "Parents",
						"message": "Bring sports kit"}).insert()

		settings = frappe.get_doc("School Settings")
		settings.update({"mpesa_enabled": 1, "mpesa_stk_enabled": 1, "mpesa_shortcode": "174379", "mpesa_passkey": "testkey",
						 "mpesa_consumer_key": "k", "mpesa_consumer_secret": "s", "mpesa_environment": "Sandbox", "portal_enabled": 1})
		settings.save()
		before = party_balance(mine.name)

		frappe.set_user(user)
		try:
			ctx = portal.portal_context()
			self.assertEqual([c["id"] for c in ctx["children"]], [mine.name])
			self.assertTrue(ctx["can_pay"])
			self.assertTrue(any(n.title == "Sports day Friday" for n in ctx["notices"]))
			with self.assertRaises(frappe.PermissionError):
				portal.assert_parent_of(other.name)
			with patch("requests.get", return_value=fake_response({"access_token": "t"})), \
				 patch("requests.post", return_value=fake_response({"ResponseCode": "0", "CheckoutRequestID": ck1,
																	 "MerchantRequestID": "m1", "CustomerMessage": "Success"})) as post:
				req = portal.pay(mine.name, 5000, phone)["request"]
			sent = post.call_args.kwargs["json"]
			self.assertEqual(sent["Amount"], 5000)
			self.assertEqual(sent["PartyA"], "254" + phone[1:])
			self.assertLessEqual(len(sent["AccountReference"]), 12)
			with self.assertRaises(frappe.PermissionError):
				portal.pay(other.name, 100, phone)
		finally:
			frappe.set_user("Administrator")

		meta = {"CallbackMetadata": {"Item": [{"Name": "Amount", "Value": 5000}, {"Name": "MpesaReceiptNumber", "Value": "TST" + frappe.generate_hash(length=7).upper()},
											   {"Name": "TransactionDate", "Value": 20261022101500}, {"Name": "PhoneNumber", "Value": int("254" + phone[1:])}]}}
		stk.apply_result(ck1, 0, "The service request is processed successfully.", stk._metadata(meta))
		stk.apply_result(ck1, 0, "again", stk._metadata(meta))  # Safaricom retry: no double posting
		r = frappe.get_doc("STK Push Request", req)
		self.assertEqual(r.status, "Paid")
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", r.mpesa_transaction, "status"), "Posted")
		self.assertEqual(party_balance(mine.name), before - 5000)

		# a cancelled prompt
		with patch("requests.get", return_value=fake_response({"access_token": "t"})), \
			 patch("requests.post", return_value=fake_response({"ResponseCode": "0", "CheckoutRequestID": ck2, "MerchantRequestID": "m2"})):
			req2 = stk.initiate(mine.name, 100, phone)
		stk.apply_result(ck2, 1032, "Request cancelled by user")
		self.assertEqual(frappe.db.get_value("STK Push Request", req2, "status"), "Cancelled")
		self.assertEqual(party_balance(mine.name), before - 5000)
