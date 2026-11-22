"""Stemic's own expenses, posted to the books (specs/features/stemic-expenses). Needs ERPNext; skipped without.
bench --site <site> run-tests --module stemic_control.tests.test_expenses"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import accounting, expenses
from stemic_control.tests.test_accounting import COMPANY, _company


class TestExpenses(TestCase):
	@classmethod
	def setUpClass(cls):
		if "erpnext" not in frappe.get_installed_apps():
			raise unittest.SkipTest("ERPNext is not installed on this site")
		super().setUpClass()
		frappe.set_user("Administrator")
		_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Stemic Settings", {"post_to_accounts": 1, "accounting_company": COMPANY})
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
		accounting.setup_accounts()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

	def expense(self, amount=6000, vat=0, mode="M-Pesa", category="Hosting & Servers", submit=True, **kw):
		doc = frappe.get_doc({"doctype": "Stemic Expense", "category": category, "paid_to": "Hetzner", "description": "Server",
							  "amount": amount, "vat_amount": vat, "mode": mode, "reference": "Q" + frappe.generate_hash(length=8).upper(),
							  **kw}).insert()
		if submit:
			doc.submit()
			doc.reload()
		return doc

	def gl(self, je):
		out = {}
		for r in frappe.get_all("GL Entry", filters={"voucher_type": "Journal Entry", "voucher_no": je, "is_cancelled": 0},
								fields=["account", "debit", "credit"]):
			out[r.account] = flt(out.get(r.account, 0) + flt(r.debit) - flt(r.credit), 2)
		return out

	def test_categories_with_their_accounts(self):
		made = expenses.ensure_categories(COMPANY)
		self.assertEqual(len(made), len(expenses.CATEGORIES))
		acc = frappe.db.get_value("Stemic Expense Category", "SMS & Messaging", "expense_account")
		self.assertEqual(frappe.db.get_value("Account", acc, ["root_type", "company"]), ("Expense", COMPANY))

	def test_expense_posts_with_vat(self):
		doc = self.expense(11600, vat=1600, mode="Bank Transfer")
		lines = self.gl(doc.journal_entry)
		hosting = frappe.db.get_value("Stemic Expense Category", "Hosting & Servers", "expense_account")
		self.assertEqual(lines[hosting], 10000)
		self.assertEqual(lines[accounting._ensure_account(COMPANY, *expenses.INPUT_VAT)], 1600)
		self.assertEqual(lines[accounting.account(COMPANY, "bank")], -11600)

	def test_cash_and_mpesa_accounts(self):
		self.assertEqual(self.gl(self.expense(500, mode="Cash").journal_entry)[accounting.account(COMPANY, "cash")], -500)
		self.assertEqual(self.gl(self.expense(700).journal_entry)[accounting.account(COMPANY, "mpesa")], -700)

	def test_cancel_reverses(self):
		doc = self.expense(900)
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus"), 2)

	def test_refused_without_company_and_bad_vat(self):
		self.assertRaises(frappe.ValidationError, self.expense, 1000, vat=1000)
		draft = self.expense(1000, submit=False)
		frappe.db.set_single_value("Stemic Settings", "accounting_company", None)
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
		self.assertRaises(frappe.ValidationError, draft.submit)

	def test_monthly_repeat_makes_one_draft(self):
		doc = self.expense(3000, repeat_monthly=1, posting_date=add_months(nowdate(), -1))
		self.assertEqual(getdate(doc.next_repeat_on), getdate(nowdate()))
		with patch("stemic_control.alerts.notify_admins") as alert:
			made = expenses.daily()
			self.assertEqual(expenses.daily(), [])  # once
		copy = frappe.get_doc("Stemic Expense", made[0])
		self.assertEqual((copy.docstatus, copy.repeated_from, copy.repeat_monthly, getdate(copy.posting_date)),
						 (0, doc.name, 1, getdate(nowdate())))
		self.assertIn("ready to confirm", alert.call_args.args[0])

	def test_unposted_and_post_missing(self):
		doc = self.expense(400)
		frappe.db.set_value("Stemic Expense", doc.name, "journal_entry", None)
		self.assertIn(doc.name, [u["name"] for u in accounting.unposted()])
		self.assertIn(doc.name, accounting.post_missing()["posted"])
		self.assertTrue(frappe.db.get_value("Stemic Expense", doc.name, "journal_entry"))

	def test_month_summary_and_report(self):
		self.expense(2000, category="SMS & Messaging")
		r = expenses.month_summary()
		self.assertGreaterEqual(r["costs"], 2000)
		self.assertIn("SMS & Messaging", [c.category for c in r["categories"]])
		from stemic_control.stemic_control.report.costs_vs_revenue.costs_vs_revenue import execute

		columns, data, _m, _chart, summary = execute({"from_date": add_days(nowdate(), -40), "to_date": nowdate()})
		self.assertIn("sms_messaging", [c["fieldname"] for c in columns])
		self.assertTrue(any(flt(r.get("sms_messaging")) >= 2000 for r in data))
