"""End-to-end test on a real site.

    bench --site test.localhost set-config allow_tests true
    bench --site test.localhost run-tests --app school_erp

Covers: setup, student -> customer, billing, targeted payment -> Payment Entry, statement, license blocking, timetable clash.
"""

from unittest.mock import patch

import frappe
from frappe.utils import flt, getdate, nowdate

try:  # v15+
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # older
	from frappe.tests.utils import FrappeTestCase as TestCase

import school_erp.licensing as licensing
from school_erp.logic import license as lic

PRIV, PUB = lic.generate_keypair()
ALL_MODULES = list(lic.MODULES)


def set_license(modules):
	key = lic.issue({"school": "Test School", "modules": modules}, PRIV)
	frappe.db.set_single_value("School Settings", "license_key", key)
	licensing.clear_cache()


def setup_school(cls):
	"""Shared by all school test classes: license, settings, setup wizard data, a term, a stream, fees."""
	cls._pub = patch.object(licensing, "PUBLIC_KEY", PUB)
	cls._pub.start()
	from school_erp.tests.utils import TEST_COMPANY, before_tests

	before_tests()
	company = TEST_COMPANY
	cls.company = company

	settings = frappe.get_doc("School Settings")
	settings.update({
		"school_name": "Test School",
		"company": company,
		"education_system": "CBC (PP1 - Grade 9)",
		"paybill_number": "123456",
		"auto_sms_on_payment": 0,
		"notify_after_billing": 0,
		"email_statement_after_billing": 0,
		"license_key": lic.issue({"school": "Test School", "modules": ALL_MODULES}, PRIV),
	})
	settings.save()
	licensing.clear_cache()

	from school_erp.api.setup import run_setup

	run_setup()

	# a payment mode with an account, so Payment Entries can post
	cash = frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0})
	if not frappe.db.exists("Mode of Payment", "_Test School Cash"):
		frappe.get_doc({
			"doctype": "Mode of Payment", "mode_of_payment": "_Test School Cash", "type": "Cash",
			"accounts": [{"company": company, "default_account": cash}],
		}).insert()
	frappe.db.set_single_value("School Settings", "default_mode_of_payment", "_Test School Cash")

	# Paybill auto-posting into the same test cash account
	settings = frappe.get_doc("School Settings")
	settings.update({"mpesa_enabled": 1, "mpesa_environment": "Sandbox", "mpesa_shortcode": "600000",
					 "mpesa_mode_of_payment": "_Test School Cash"})
	settings.save()

	year = str(getdate(nowdate()).year)
	cls.term = frappe.db.get_value("School Term", {"school_year": year, "start_date": ("<=", nowdate()), "term_name": ("like", "Term %")},
								   "name", order_by="start_date desc") or f"Term 1 {year}"

	if not frappe.db.exists("Stream", "Grade 4 Test"):
		frappe.get_doc({"doctype": "Stream", "school_class": "Grade 4", "stream_name": "Test"}).insert()
	if not frappe.db.exists("Transport Route", "_Test Route"):
		frappe.get_doc({"doctype": "Transport Route", "route_name": "_Test Route", "fee_per_term": 9000,
						"fee_type": "Transport"}).insert()
	if not frappe.db.exists("School Fee Structure", {"school_term": cls.term, "school_class": "Grade 4"}):
		frappe.get_doc({
			"doctype": "School Fee Structure", "school_term": cls.term, "school_class": "Grade 4", "boarding_type": "All",
			"items": [{"fee_type": "Tuition", "amount": 25000}, {"fee_type": "Lunch", "amount": 6000}],
		}).insert()
	frappe.db.commit()



class TestSchoolFlow(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def make_student(self, **kw):
		doc = frappe.get_doc({
			"doctype": "Student", "first_name": "amani", "last_name": "test", "stream": "Grade 4 Test",
			"takes_lunch": 1, "transport_route": "_Test Route",
			"guardians": [{"guardian_name": "Grace Test", "relation": "Mother", "mobile_no": "0712345678", "email": "grace@example.com"}],
			**kw,
		}).insert()
		return doc

	# ------------------------------------------------------------------
	def test_student_becomes_customer_with_same_id(self):
		s = self.make_student()
		self.assertEqual(s.student_name, "Amani Test")
		self.assertEqual(s.customer, s.name)
		self.assertEqual(frappe.db.get_value("Customer", s.name, "student"), s.name)
		self.assertEqual(s.primary_guardian, "Grace Test")

	def test_bill_pay_and_statement(self):
		from school_erp.api.billing import bill_single_student
		from school_erp.api.payments import get_open_balances, party_balance
		from school_erp.api.statement import build_statement, render_fee_statement

		s = self.make_student()
		inv = bill_single_student(s.name, self.term)
		si = frappe.get_doc("Sales Invoice", inv)
		self.assertEqual(si.docstatus, 1)
		self.assertEqual(flt(si.grand_total), 40000)  # 25000 tuition + 6000 lunch + 9000 transport
		self.assertEqual({i.fee_type for i in si.items}, {"Tuition", "Lunch", "Transport"})

		with self.assertRaises(frappe.ValidationError):  # never billed twice
			bill_single_student(s.name, self.term)

		fp = frappe.get_doc({
			"doctype": "Fee Payment", "student": s.name, "amount": 12000, "reference_no": f"T{frappe.generate_hash(length=8)}",
			"allocation_method": "Specific fee types", "target_fee_types": [{"fee_type": "Transport"}], "apply_remainder": 1,
		}).insert()
		alloc = {a.fee_type: flt(a.allocated_amount) for a in fp.allocations}
		self.assertEqual(alloc, {"Transport": 9000, "Tuition": 3000})
		fp.submit()
		self.assertTrue(fp.payment_entry)
		self.assertEqual(frappe.db.get_value("Payment Entry", fp.payment_entry, "docstatus"), 1)
		self.assertEqual(party_balance(s.name), 28000)

		owed = {r["fee_type"]: r["outstanding"] for r in get_open_balances(s.name)["by_fee_type"]}
		self.assertEqual(owed, {"Tuition": 22000, "Lunch": 6000})

		data = build_statement(s.name)
		self.assertEqual(data["ledger"]["closing"], 28000)
		self.assertEqual(data["breakdown"]["total"]["outstanding"], 28000)
		html = render_fee_statement(s.name)
		self.assertIn(s.name, html)
		self.assertIn("123456", html)

		# duplicate M-Pesa code rejected
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Fee Payment", "student": s.name, "amount": 100, "reference_no": fp.reference_no}).insert()

		# cancelling the fee payment reverses the accounting
		fp.reload()
		fp.cancel()
		self.assertEqual(frappe.db.get_value("Payment Entry", fp.payment_entry, "docstatus"), 2)
		self.assertEqual(party_balance(s.name), 40000)

	def test_license_blocks_unpaid_modules(self):
		try:
			set_license(["fees"])
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Transport Route", "route_name": "_Blocked Route", "fee_per_term": 1,
								"fee_type": "Transport"}).insert()
			with self.assertRaises(frappe.PermissionError):
				self.make_student()  # student uses transport + lunch, not licensed
		finally:
			set_license(ALL_MODULES)

	def test_student_limit_says_how_many_the_school_has(self):
		active = frappe.db.count("Student", {"status": "Active"})
		try:
			key = lic.issue({"school": "Test School", "modules": ALL_MODULES, "max_students": max(active, 1)}, PRIV)
			frappe.db.set_single_value("School Settings", "license_key", key)
			licensing.clear_cache()
			if not active:
				self.make_student()
			with self.assertRaises(frappe.ValidationError) as caught:
				self.make_student()
			self.assertIn(f"allows {max(active, 1)} active students and the school has {max(active, 1)}", str(caught.exception))
		finally:
			set_license(ALL_MODULES)

	def test_unlicensed_modules_cannot_be_seen(self):
		"""Not only unsaveable: a module the license leaves out is hidden from reads, lists and search."""
		from frappe.boot import get_bootinfo

		route = frappe.get_doc({"doctype": "Transport Route", "route_name": "_Hidden " + frappe.generate_hash(length=5),
								"fee_per_term": 1, "fee_type": "Transport"}).insert()
		user = f"admin-{frappe.generate_hash(length=6)}@licence.test"
		frappe.get_doc({"doctype": "User", "email": user, "first_name": "Licence", "send_welcome_email": 0,
						"roles": [{"role": "School Admin"}]}).insert(ignore_permissions=True)
		try:
			set_license(["exams"])  # no fees, transport or timetable
			frappe.set_user(user)
			self.assertFalse(frappe.has_permission("Transport Route", "read", route.name))
			self.assertRaises(frappe.PermissionError, frappe.get_doc("Transport Route", route.name).check_permission, "read")
			self.assertEqual(frappe.get_list("Transport Route", pluck="name"), [])
			self.assertEqual(frappe.get_list("Fee Payment", pluck="name"), [])
			self.assertTrue(frappe.get_list("Subject", limit=1))  # timetable is off, but exams need subjects
			can_read = get_bootinfo()["user"]["can_read"]
			self.assertNotIn("Transport Route", can_read)  # so search and the desk do not offer it
			self.assertIn("Subject", can_read)

			frappe.set_user("Administrator")
			set_license(ALL_MODULES)  # licensed again: everything comes back, nothing was lost
			frappe.set_user(user)
			self.assertTrue(frappe.has_permission("Transport Route", "read", route.name))
			self.assertIn(route.name, frappe.get_list("Transport Route", pluck="name"))
		finally:
			frappe.set_user("Administrator")
			set_license(ALL_MODULES)

	def test_timetable_teacher_clash(self):
		t = frappe.get_doc({"doctype": "Teacher", "teacher_name": "Mr Clash"}).insert()
		if not frappe.db.exists("Stream", "Grade 5 Test"):
			frappe.get_doc({"doctype": "Stream", "school_class": "Grade 5", "stream_name": "Test"}).insert()
		for name in ("Grade 4 Test - " + self.term, "Grade 5 Test - " + self.term):
			frappe.delete_doc_if_exists("Timetable", name)
		slot = {"day": "Monday", "period": "P1", "subject": "Mathematics", "teacher": t.name}
		frappe.get_doc({"doctype": "Timetable", "stream": "Grade 4 Test", "school_term": self.term, "slots": [slot]}).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Timetable", "stream": "Grade 5 Test", "school_term": self.term, "slots": [slot]}).insert()

	# ------------------------------------------------------------------ M-Pesa Paybill
	def paybill_payload(self, ref, amount, code=None):
		return {
			"TransactionType": "Pay Bill", "TransID": code or ("T" + frappe.generate_hash(length=9).upper()),
			"TransTime": "20261021153045", "TransAmount": str(amount), "BusinessShortCode": "600000",
			"BillRefNumber": ref, "MSISDN": "2547 ***** 126", "FirstName": "GRACE", "LastName": "TEST",
		}

	def test_paybill_auto_posts_and_is_idempotent(self):
		from school_erp.api.billing import bill_single_student
		from school_erp.api.paybill import record_confirmation
		from school_erp.api.payments import party_balance

		s = self.make_student()
		bill_single_student(s.name, self.term)
		messy_ref = s.name.lower().replace("-", " ")  # parent typed "stu 2026 0007"
		payload = self.paybill_payload(messy_ref, 15000)
		name = record_confirmation(payload)

		tx = frappe.get_doc("M-Pesa Transaction", name)
		self.assertEqual(tx.status, "Posted", tx.error)
		self.assertEqual(tx.student, s.name)
		self.assertEqual(frappe.db.get_value("Fee Payment", tx.fee_payment, "docstatus"), 1)
		self.assertEqual(party_balance(s.name), 25000)

		record_confirmation(payload)  # Safaricom retries the same callback
		self.assertEqual(frappe.db.count("Fee Payment", {"reference_no": payload["TransID"], "docstatus": 1}), 1)
		self.assertEqual(party_balance(s.name), 25000)

		# cancelling the receipt hands it back to the bursar and is not re-posted by the retry job
		fp = frappe.get_doc("Fee Payment", tx.fee_payment)
		fp.cancel()
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Ignored")
		from school_erp.api.paybill import retry_pending

		retry_pending()
		self.assertEqual(party_balance(s.name), 40000)

	def test_paybill_unmatched_then_assigned(self):
		from school_erp.api.paybill import assign_and_post, record_confirmation

		s = self.make_student()
		name = record_confirmation(self.paybill_payload("WRONG123", 5000))
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Unmatched")
		result = assign_and_post(name, s.name)
		self.assertEqual(result["status"], "Posted", result.get("error"))
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "student"), s.name)

	def test_paybill_callback_token_read_from_url_of_json_post(self):
		"""Safaricom posts JSON with the token in the query string; Frappe leaves it out of form_dict."""
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from school_erp.api.paybill import _authorised

		settings = frappe.get_doc("School Settings")
		settings.mpesa_callback_token = "callback-test-token"
		previous = getattr(frappe.local, "request", None), frappe.local.form_dict
		try:
			for token, expected in (("callback-test-token", None), ("wrong", "bad token")):
				frappe.local.request = Request(EnvironBuilder(method="POST", query_string={"token": token}, json={"TransID": "X"}).get_environ())
				frappe.local.form_dict = frappe._dict({"TransID": "X"})  # what make_form_dict gives for a JSON body
				self.assertEqual(_authorised(settings), expected)
		finally:
			frappe.local.request, frappe.local.form_dict = previous

	def use_till(self, store="7712345", till="8812345"):
		"""Switch School Settings to a Till for one test; returns a function that switches back."""
		fields = ("mpesa_account_type", "mpesa_shortcode", "paybill_number")
		before = {f: frappe.db.get_single_value("School Settings", f) for f in fields}
		for f, v in zip(fields, ("Till (Buy Goods)", store, till)):
			frappe.db.set_single_value("School Settings", f, v)
		frappe.clear_document_cache("School Settings", "School Settings")

		def restore():
			for f, v in before.items():
				frappe.db.set_single_value("School Settings", f, v)
			frappe.clear_document_cache("School Settings", "School Settings")
		return restore

	def test_refused_confirmation_is_held_for_the_bursar(self):
		from school_erp.api.paybill import assign_and_post, hold_for_review, retry_pending
		from school_erp.logic.paybill import confirmation_problems

		s = self.make_student()
		raw = {**self.paybill_payload(s.name, 800), "BusinessShortCode": "999999"}  # a short code that is not ours
		problems = confirmation_problems(raw, "600000")
		name = hold_for_review(raw, problems)
		tx = frappe.get_doc("M-Pesa Transaction", name)
		self.assertEqual((tx.status, tx.fee_payment), ("Needs Review", None))
		self.assertIn("999999", tx.error)
		self.assertEqual(hold_for_review(raw, problems), name)  # a retry is acknowledged, not duplicated
		self.assertEqual(frappe.db.count("M-Pesa Transaction", {"trans_id": raw["TransID"]}), 1)

		retry_pending()  # never posted automatically
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Needs Review")

		self.assertRaises(frappe.ValidationError, assign_and_post, name, s.name)  # not without saying what was checked
		bursar = "bursar-" + frappe.generate_hash(length=6) + "@school.test"
		frappe.get_doc({"doctype": "User", "email": bursar, "first_name": "Bursar", "send_welcome_email": 0,
						"roles": [{"role": "Bursar"}]}).insert(ignore_permissions=True)
		frappe.set_user(bursar)
		try:  # a bursar alone cannot release it
			self.assertRaises(frappe.PermissionError, assign_and_post, name, s.name, "STMT-OCT-17", "Seen on the statement")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Needs Review")

		out = assign_and_post(name, s.name, "STMT-OCT-17 line 42", "Amount and payer match the Safaricom statement")
		self.assertEqual(out["status"], "Posted")
		tx.reload()
		self.assertEqual((tx.verified_reference, tx.verified_by), ("STMT-OCT-17 line 42", "Administrator"))
		self.assertIsNone(hold_for_review({**raw, "TransID": ""}, problems))  # nothing to key it on: log only

	def test_till_payment_matched_by_payer_phone(self):
		from school_erp.api.paybill import record_confirmation

		phone = "0733" + frappe.generate_hash(length=6).translate(str.maketrans("abcdef", "123456"))[:6]
		s = self.make_student(guardians=[{"guardian_name": "Till Parent", "relation": "Mother", "mobile_no": phone}])
		restore = self.use_till()
		try:
			till_payment = lambda msisdn, code="8812345": {**self.paybill_payload("", 700), "TransactionType": "Buy Goods",
													   "BusinessShortCode": code, "MSISDN": msisdn}
			name = record_confirmation(till_payment("254" + phone[1:]))  # no account number: matched by phone
			tx = frappe.get_doc("M-Pesa Transaction", name)
			self.assertEqual((tx.status, tx.student), ("Posted", s.name), tx.error)

			masked = record_confirmation(till_payment("2547 ***** 126"))  # how Safaricom usually sends it
			self.assertEqual(frappe.db.get_value("M-Pesa Transaction", masked, "status"), "Unmatched")

			self.make_student()  # two students share the fixture's 0712345678: the bursar must choose
			self.make_student()
			shared = record_confirmation(till_payment("254712345678", code="7712345"))  # reported by store number
			self.assertEqual(frappe.db.get_value("M-Pesa Transaction", shared, "status"), "Unmatched")
			self.assertRaises(frappe.ValidationError, record_confirmation, till_payment("254712345678", code="999999"))
		finally:
			restore()

	def test_stk_push_to_a_till(self):
		from school_erp.api import stk

		s = self.make_student()
		restore = self.use_till()
		settings = frappe.get_doc("School Settings")
		settings.update({"mpesa_enabled": 1, "mpesa_stk_enabled": 1, "mpesa_passkey": "testkey", "mpesa_consumer_key": "k",
						 "mpesa_consumer_secret": "s", "mpesa_environment": "Sandbox"})
		settings.save()
		ok = lambda body: type("R", (), {"status_code": 200, "text": "x", "json": lambda self: body})()
		try:
			with patch("requests.get", return_value=ok({"access_token": "t"})), \
				 patch("requests.post", return_value=ok({"ResponseCode": "0", "CheckoutRequestID": "ws_CO_" + frappe.generate_hash(length=8),
														  "MerchantRequestID": "m1"})) as post:
				stk.initiate(s.name, 500, "0712345678")
			sent = post.call_args.kwargs["json"]
			self.assertEqual(sent["TransactionType"], "CustomerBuyGoodsOnline")
			self.assertEqual((sent["BusinessShortCode"], sent["PartyB"]), ("7712345", "8812345"))
		finally:
			restore()

	def test_paybill_needs_license(self):
		from school_erp.api.paybill import record_confirmation

		s = self.make_student()
		try:
			set_license([m for m in ALL_MODULES if m != "mpesa"])
			name = record_confirmation(self.paybill_payload(s.name, 1000))
			self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Failed")
		finally:
			set_license(ALL_MODULES)
