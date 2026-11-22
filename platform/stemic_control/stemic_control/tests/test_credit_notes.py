"""Credit notes and refunds on subscription invoices (specs/features/credit-notes). Needs ERPNext; skipped without.
bench --site <site> run-tests --module stemic_control.tests.test_credit_notes"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, nowdate

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import accounting, api, billing
from stemic_control.tests.test_accounting import COMPANY, _company


class TestCreditNotes(TestCase):
	@classmethod
	def setUpClass(cls):
		if "erpnext" not in frappe.get_installed_apps():
			raise unittest.SkipTest("ERPNext is not installed on this site")
		super().setUpClass()
		frappe.set_user("Administrator")
		_company()

	def setUp(self):
		frappe.set_user("Administrator")
		self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
		self._conf.start()
		frappe.db.set_single_value("Stemic Settings", {"post_to_accounts": 1, "accounting_company": COMPANY})
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
		frappe.db.set_single_value("Stemic Tax Settings", {"tax_treatment": "Standard Rated", "vat_rate": 16})
		frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")
		slug = "cn-" + frappe.generate_hash(length=6).lower()
		self.tenant = api.register_tenant("Credit Academy", slug, "head@credit.test")
		plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "CN " + frappe.generate_hash(length=5), "enabled": 1,
							   "monthly_price": 5800, "student_limit": 400, "modules": "[]"}).insert().name
		sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": plan, "starts_on": nowdate(),
							  "ends_on": add_days(nowdate(), 10)}).insert().name
		self.inv = billing.create_invoice(sub, months=1)  # 5,800 incl. VAT 800

	def tearDown(self):
		self._conf.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
		frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")

	def pay(self, amount):
		return billing.record_payment(self.inv, amount, "M-Pesa", "Q" + frappe.generate_hash(length=8).upper())["payment"]

	def credit(self, amount, refund=0, submit=True, reason="Billing error"):
		doc = frappe.get_doc({"doctype": "SaaS Credit Note", "invoice": self.inv, "amount": amount, "reason": reason,
							  "refund": 1 if refund else 0, "refund_amount": refund, "refund_mode": "M-Pesa" if refund else None,
							  "refund_reference": "R" + frappe.generate_hash(length=8).upper() if refund else None}).insert()
		if submit:
			doc.submit()
			doc.reload()
		return doc

	def inv_state(self):
		return frappe.db.get_value("SaaS Invoice", self.inv, ["outstanding", "credited_amount", "refunded_amount", "status"])

	def test_partial_credit_reduces_what_is_owed(self):
		cn = self.credit(1160)
		self.assertEqual(self.inv_state(), (4640, 1160, 0, "Unpaid"))
		ret = frappe.get_doc("Sales Invoice", cn.return_invoice)
		self.assertEqual((ret.is_return, flt(ret.grand_total)), (1, -1160))
		vat = accounting.account(COMPANY, "vat")
		vat_lines = frappe.get_all("GL Entry", filters={"voucher_no": ret.name, "account": vat, "is_cancelled": 0}, fields=["debit"])
		self.assertEqual(flt(sum(flt(r.debit) for r in vat_lines), 2), 160)  # 16% VAT inside 1,160 reversed
		si = frappe.db.get_value("SaaS Invoice", self.inv, "sales_invoice")
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", si, "outstanding_amount")), 4640)
		self.assertFalse(accounting.ledger_check()["mismatches"] and
						 [m for m in accounting.ledger_check()["mismatches"] if m["name"] == self.inv])

	def test_full_credit_marks_credited(self):
		self.credit(5800)
		self.assertEqual(self.inv_state()[3], "Credited")
		self.assertRaises(frappe.ValidationError, self.credit, 1)  # nothing left to credit

	def test_refund_of_overpayment(self):
		self.pay(5800)
		cn = self.credit(2000, refund=2000, reason="Discount after invoicing")
		self.assertEqual(self.inv_state(), (0, 2000, 2000, "Paid"))
		pe = frappe.get_doc("Payment Entry", cn.refund_entry)
		self.assertEqual((pe.payment_type, flt(pe.paid_amount), pe.paid_from), ("Pay", 2000, accounting.account(COMPANY, "mpesa")))

	def test_refund_limited_to_money_overpaid(self):
		self.pay(3000)
		# after a 2,000 credit the school owes 3,800 and has paid 3,000: nothing to refund
		self.assertRaises(frappe.ValidationError, self.credit, 2000, 500)
		self.pay(2800)  # now paid 5,800
		self.assertRaises(frappe.ValidationError, self.credit, 1000, 1500)  # refund larger than the credit

	def test_cancel_reverses_both(self):
		self.pay(5800)
		cn = self.credit(1000, refund=1000)
		cn.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", cn.return_invoice, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Payment Entry", cn.refund_entry, "docstatus"), 2)
		self.assertEqual(self.inv_state(), (0, 0, 0, "Paid"))

	def test_invoice_cannot_be_cancelled_with_credit_notes(self):
		self.credit(500)
		inv = frappe.get_doc("SaaS Invoice", self.inv)
		self.assertRaises(frappe.ValidationError, inv.cancel)

	def test_kra_credit_note_flagged(self):
		frappe.get_doc({"doctype": "SaaS eTIMS Invoice", "tenant": self.tenant, "saas_invoice": self.inv, "status": "Submitted",
						"external_invoice_no": self.inv, "buyer_name": "Credit Academy", "net_amount": 5000, "vat_amount": 800,
						"total_amount": 5800, "tax_treatment": "Standard Rated", "seller_scope": "Platform"}).db_insert()
		with patch("stemic_control.alerts.notify_admins") as alert:
			cn = self.credit(580)
		self.assertEqual(cn.tax_credit_status, "Needed")
		self.assertIn("KRA credit note needed", alert.call_args_list[0].args[0])
		cn.kra_credit_reference = "KRACN0001"
		cn.save()
		self.assertEqual(frappe.db.get_value("SaaS Credit Note", cn.name, "tax_credit_status"), "Done")

	def test_payment_cannot_exceed_balance_after_credit(self):
		self.credit(5000)
		self.assertRaises(frappe.ValidationError, self.pay, 1000)  # only 800 owed
		self.pay(800)
		self.assertEqual(self.inv_state()[3], "Paid")
