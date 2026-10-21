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


class TestSchoolFlow(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
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
		cls.term = frappe.db.get_value("School Term", {"school_year": year, "start_date": ("<=", nowdate())},
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

	def test_paybill_needs_license(self):
		from school_erp.api.paybill import record_confirmation

		s = self.make_student()
		try:
			set_license([m for m in ALL_MODULES if m != "mpesa"])
			name = record_confirmation(self.paybill_payload(s.name, 1000))
			self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Failed")
		finally:
			set_license(ALL_MODULES)
