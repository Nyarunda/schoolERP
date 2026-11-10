"""Bench tests: pocket money deposits, spending rules, cancelling, the portal view, reports."""

from unittest.mock import patch

import frappe

from school_erp.tests.test_integration import TestCase, setup_school


class TestPocketMoneyFlow(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def kid(self, first):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Pocket", "stream": "Grade 4 Test", "gender": "Female",
			"guardians": [{"guardian_name": "Mama " + first, "relation": "Mother", "mobile_no": "0712345678"}],
		}).insert().name

	def txn(self, student, kind, amount, **kw):
		doc = frappe.get_doc({"doctype": "Pocket Money Transaction", "student": student, "transaction_type": kind,
							  "amount": amount, **kw}).insert()
		doc.submit()
		return doc

	def balance(self, student):
		return frappe.db.get_value("Pocket Money Account", student, "balance")

	def test_deposit_spend_and_limits(self):
		s = self.kid("Neema")
		with self.assertRaises(frappe.ValidationError):
			self.txn(s, "Purchase", 10)  # no account yet
		with patch("school_erp.api.messaging.send_sms", return_value={"sent": ["x"], "failed": []}) as sms:
			self.txn(s, "Deposit", 1000, mode="M-Pesa", reference="qwe 123 rty")
		self.assertTrue(sms.called)
		self.assertEqual(self.balance(s), 1000)
		with self.assertRaises(frappe.ValidationError):
			self.txn(s, "Deposit", 50, mode="M-Pesa", reference="QWE123RTY")  # same M-Pesa code twice
		self.txn(s, "Purchase", 300, description="Canteen")
		with self.assertRaises(frappe.ValidationError):
			self.txn(s, "Purchase", 800)  # more than the balance
		acct = frappe.get_doc("Pocket Money Account", s)
		acct.daily_limit = 400
		acct.balance = 999999  # ignored: only transactions change the balance
		acct.save()
		self.assertEqual(self.balance(s), 700)
		with self.assertRaises(frappe.ValidationError):
			self.txn(s, "Purchase", 150)  # 300 + 150 > 400 today
		self.txn(s, "Purchase", 100)
		self.assertEqual(self.balance(s), 600)

	def test_cancel_rules(self):
		s = self.kid("Imani")
		dep = self.txn(s, "Deposit", 200)
		buy = self.txn(s, "Purchase", 150)
		with self.assertRaises(frappe.ValidationError):
			dep.cancel()  # 150 of it is already spent
		buy.cancel()
		self.assertEqual(self.balance(s), 200)
		dep.reload()
		dep.cancel()
		self.assertEqual(self.balance(s), 0)

	def test_frozen_account_and_portal(self):
		from school_erp.api.pocket_money import portal_pocket_money, recalculate

		s = self.kid("Zawadi")
		self.txn(s, "Deposit", 500)
		acct = frappe.get_doc("Pocket Money Account", s)
		acct.update({"is_frozen": 1, "frozen_reason": "Parent request"})
		acct.save()
		with self.assertRaises(frappe.ValidationError):
			self.txn(s, "Purchase", 10)
		view = portal_pocket_money(s)
		self.assertEqual((view["balance"], view["frozen"], view["recent"][0]["amount"]), (500, True, 500))
		frappe.db.set_value("Pocket Money Account", s, "balance", 1)
		self.assertEqual(recalculate(s)["balance"], 500)

	def test_reports(self):
		from school_erp.school.report.pocket_money_balances.pocket_money_balances import execute as balances
		from school_erp.school.report.pocket_money_statement.pocket_money_statement import execute as statement

		s = self.kid("Baraka")
		self.txn(s, "Deposit", 300)
		self.txn(s, "Purchase", 120)
		_c, rows, *_ = statement({"student": s})
		self.assertEqual(rows[-1]["balance"], 180)
		_c, rows, *_ = balances({})
		self.assertTrue(any(r["student"] == s for r in rows))
