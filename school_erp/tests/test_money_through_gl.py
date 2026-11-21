"""Every shilling through the General Ledger (specs/features/money-through-gl).
bench --site <site> run-tests --module school_erp.tests.test_money_through_gl"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, now_datetime, nowdate

from school_erp.api import ledger
from school_erp.tests.test_integration import TestCase, setup_school

NOTIFY = "school_erp.api.notify.notify"


class TestMoneyThroughGL(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.set_user("Administrator")
		settings = frappe.get_doc("School Settings")
		settings.save()  # fills in the ledger accounts
		bank = frappe.db.get_value("Account", {"company": cls.company, "account_type": "Bank", "is_group": 0})
		if not bank:
			group = (frappe.db.get_value("Account", {"company": cls.company, "account_name": "Bank Accounts", "is_group": 1})
					 or frappe.db.get_value("Account", {"company": cls.company, "account_name": "Current Assets", "is_group": 1}))
			bank = frappe.get_doc({"doctype": "Account", "account_name": "_Test PM Bank Account", "parent_account": group,
								   "company": cls.company, "account_type": "Bank"}).insert().name
		if not frappe.db.exists("Mode of Payment", "_Test PM Bank"):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "_Test PM Bank", "type": "Bank",
							"accounts": [{"company": cls.company, "default_account": bank}]}).insert()
		frappe.db.set_single_value("School Settings", "pocket_money_bank_mode", "_Test PM Bank")
		frappe.clear_document_cache("School Settings", "School Settings")
		cls.bank = bank
		cls.cash = frappe.db.get_value("Account", {"company": cls.company, "account_type": "Cash", "is_group": 0})
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._pub.stop()
		super().tearDownClass()

	# ------------------------------------------------------------------ helpers
	def setting(self, field):
		return frappe.get_cached_doc("School Settings").get(field)

	def set_setting(self, field, value):
		frappe.db.set_single_value("School Settings", field, value)
		frappe.clear_document_cache("School Settings", "School Settings")

	def kid(self, first="Ledger"):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Money", "stream": "Grade 4 Test", "gender": "Male",
			"guardians": [{"guardian_name": "Baba " + first, "relation": "Father", "mobile_no": "0712345670"}],
		}).insert().name

	def txn(self, student, kind, amount, **kw):
		doc = frappe.get_doc({"doctype": "Pocket Money Transaction", "student": student, "transaction_type": kind,
							  "amount": amount, **kw}).insert()
		with patch("school_erp.api.pocket_money._queue_sms"):
			doc.submit()
		doc.reload()
		return doc

	def lines(self, je):
		"""{account: debit - credit} of one submitted journal entry."""
		out = {}
		for r in frappe.get_all("GL Entry", filters={"voucher_type": "Journal Entry", "voucher_no": je, "is_cancelled": 0},
								fields=["account", "debit", "credit"]):
			out[r.account] = round(out.get(r.account, 0) + flt(r.debit) - flt(r.credit), 2)
		return out

	# ------------------------------------------------------------------ pocket money
	def test_accounts_created(self):
		for field, (name, root, _groups) in ledger.ACCOUNTS.items():
			acc = self.setting(field)
			self.assertTrue(acc, field)
			self.assertEqual(frappe.db.get_value("Account", acc, ["account_name", "root_type", "is_group"]), (name, root, 0))
		self.assertEqual(self.setting("fuel_expense_category"), "Fuel")
		self.assertEqual(self.setting("pocket_money_purchase_posting"), "Daily summary")

	def test_deposit_posts(self):
		s = self.kid()
		dep = self.txn(s, "Deposit", 500, mode="Cash")
		self.assertTrue(dep.journal_entry)
		self.assertEqual(self.lines(dep.journal_entry), {self.cash: 500, self.setting("pocket_money_account"): -500})

	def test_deposit_bank_account(self):
		s = self.kid()
		dep = self.txn(s, "Deposit", 300, mode="Bank", reference="BNK" + frappe.generate_hash(length=6).upper())
		self.assertEqual(self.lines(dep.journal_entry).get(self.bank), 300)

	def test_withdrawal_posts(self):
		s = self.kid()
		self.txn(s, "Deposit", 500)
		w = self.txn(s, "Withdrawal", 200)
		self.assertEqual(self.lines(w.journal_entry), {self.setting("pocket_money_account"): 200, self.cash: -200})

	def test_purchase_each(self):
		self.set_setting("pocket_money_purchase_posting", "Each purchase")
		try:
			s = self.kid()
			self.txn(s, "Deposit", 500)
			buy = self.txn(s, "Purchase", 120, description="Mandazi")
			self.assertEqual(self.lines(buy.journal_entry),
							 {self.setting("pocket_money_account"): 120, self.setting("tuck_shop_income_account"): -120})
		finally:
			self.set_setting("pocket_money_purchase_posting", "Daily summary")

	def test_purchase_daily_summary(self):
		s = self.kid()
		day = add_days(now_datetime(), -2)
		self.txn(s, "Deposit", 1000, posting_datetime=add_days(day, -1))
		buys = [self.txn(s, "Purchase", amt, posting_datetime=day) for amt in (50, 70, 30)]
		self.assertTrue(all(not b.journal_entry for b in buys))  # waiting for the day's summary
		made = ledger.post_purchase_summaries()
		entries = {frappe.db.get_value("Pocket Money Transaction", b.name, "journal_entry") for b in buys}
		self.assertEqual(len(entries), 1)
		je = entries.pop()
		self.assertIn(je, made)
		self.assertEqual(self.lines(je).get(self.setting("tuck_shop_income_account")), -150)
		self.assertEqual(ledger.post_purchase_summaries(), [])  # nothing posted twice

	def test_cancel_reverses(self):
		s = self.kid()
		dep = self.txn(s, "Deposit", 400)
		dep.cancel()
		dep.reload()
		self.assertTrue(dep.reversal_entry)
		held = self.setting("pocket_money_account")
		self.assertEqual(self.lines(dep.journal_entry)[held] + self.lines(dep.reversal_entry)[held], 0)
		# a purchase still waiting for the daily summary has nothing in the books: cancelling posts nothing
		self.txn(s, "Deposit", 100)
		buy = self.txn(s, "Purchase", 60)
		buy.cancel()
		buy.reload()
		self.assertFalse(buy.reversal_entry)

	def test_reconciliation(self):
		before = ledger.pocket_money_reconciliation()
		s = self.kid()
		self.txn(s, "Deposit", 900)
		self.txn(s, "Purchase", 100)
		self.txn(s, "Withdrawal", 200)
		after = ledger.pocket_money_reconciliation()
		self.assertEqual(after["difference"], before["difference"])  # these movements keep the books in step
		self.assertEqual(round(after["learners"] - before["learners"], 2), 600)

	def test_opening_entry_once(self):
		self.set_setting("ledger_start", None)
		try:
			s = self.kid()
			self.txn(s, "Deposit", 250)
			total = flt(frappe.db.sql("select sum(balance) from `tabPocket Money Account`")[0][0], 2)
			je = ledger.post_pocket_money_opening()
			self.assertTrue(je)
			self.assertEqual(self.lines(je)[self.setting("pocket_money_account")], -total)
			self.assertEqual(ledger.post_pocket_money_opening(), je)  # once only
			self.assertEqual(frappe.db.count("Journal Entry", {"cheque_no": "PM-OPENING", "docstatus": 1}), 1)
		finally:
			ledger.cancel_journal(self.setting("pocket_money_opening_entry"))
			self.set_setting("ledger_start", None)
			self.set_setting("pocket_money_opening_entry", None)

	def test_unposted_money(self):
		s = self.kid()
		dep = self.txn(s, "Deposit", 75)
		self.assertNotIn(dep.name, [r["name"] for r in ledger.unposted_money()])
		frappe.db.set_value("Pocket Money Transaction", dep.name, "journal_entry", None)
		self.assertIn(dep.name, [r["name"] for r in ledger.unposted_money()])

	# ------------------------------------------------------------------ M-Pesa
	def test_unmatched_to_suspense_then_assigned(self):
		from school_erp.api.paybill import assign_and_post, record_confirmation

		name = record_confirmation(self.paybill_payload("NOSUCH" + frappe.generate_hash(length=4).upper(), 700))
		tx = frappe.get_doc("M-Pesa Transaction", name)
		self.assertEqual(tx.status, "Unmatched")
		self.assertTrue(tx.suspense_entry)
		self.assertEqual(self.lines(tx.suspense_entry).get(self.setting("unidentified_receipts_account")), -700)

		s = frappe.get_doc({"doctype": "Student", "first_name": "Found", "last_name": "Payer", "stream": "Grade 4 Test",
							"guardians": [{"guardian_name": "P", "relation": "Mother", "mobile_no": "0712345611"}]}).insert()
		result = assign_and_post(name, s.name)
		self.assertEqual(result["status"], "Posted", result.get("error"))
		self.assertEqual(frappe.db.get_value("Journal Entry", tx.suspense_entry, "docstatus"), 2)  # suspense cleared
		self.assertTrue(frappe.db.get_value("M-Pesa Transaction", name, "fee_payment"))

	def test_needs_review_not_posted(self):
		from school_erp.api.paybill import hold_for_review

		name = hold_for_review(self.paybill_payload("X1", 900), ["wrong short code"])
		self.assertEqual(frappe.db.get_value("M-Pesa Transaction", name, "status"), "Needs Review")
		self.assertFalse(frappe.db.get_value("M-Pesa Transaction", name, "suspense_entry"))

	def paybill_payload(self, ref, amount):
		return {"TransactionType": "Pay Bill", "TransID": "G" + frappe.generate_hash(length=9).upper(),
				"TransTime": "20261121103045", "TransAmount": str(amount), "BusinessShortCode": "600000",
				"BillRefNumber": ref, "MSISDN": "2547 ***** 126", "FirstName": "GRACE", "LastName": "TEST"}

	# ------------------------------------------------------------------ library
	def test_fine_paid(self):
		from school_erp.api.library import fine_paid

		tag = "F" + frappe.generate_hash(length=4).upper()
		book = frappe.get_doc({"doctype": "Library Book", "title": "Ledger Fines " + tag, "category": "Set Book / Literature",
							   "price": 500, "copies": [{"accession_no": tag + "-1"}, {"accession_no": tag + "-2"}]}).insert().name
		s = self.kid("Reader")
		loan = frappe.get_doc({"doctype": "Library Loan", "borrower_type": "Student", "student": s, "book": book,
							   "accession_no": tag + "-1"}).insert()
		loan.db_set({"status": "Returned", "fine_amount": 50})
		r = fine_paid(loan.name, "Cash")
		self.assertEqual(self.lines(r["entry"]), {self.cash: 50, self.setting("library_fines_account"): -50})
		with self.assertRaises(frappe.ValidationError):
			fine_paid(loan.name, "Cash")  # not twice
		with self.assertRaises(frappe.ValidationError):
			fine_paid(loan.name, "M-Pesa")  # M-Pesa needs its code

		billed = frappe.get_doc({"doctype": "Library Loan", "borrower_type": "Student", "student": self.kid("Billed"),
								 "book": book, "accession_no": tag + "-2"}).insert()
		billed.db_set({"status": "Returned", "fine_amount": 40, "fine_waived": 1})
		with self.assertRaises(frappe.ValidationError):
			fine_paid(billed.name, "Cash")  # waived

	# ------------------------------------------------------------------ fuel
	def _driver_log(self, cost):
		email = "fuel.driver@test.school"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Fuel Driver", "send_welcome_email": 0}).insert(ignore_permissions=True)
		driver = frappe.db.get_value("Staff Member", {"user": email}) or frappe.get_doc({
			"doctype": "Staff Member", "full_name": "Fuel Driver", "staff_type": "Driver", "gender": "Male",
			"phone": "0712000222", "user": email}).insert().name
		if not frappe.db.exists("School Vehicle", "KFUEL 001F"):
			frappe.get_doc({"doctype": "School Vehicle", "registration_number": "KFUEL 001F", "default_driver": driver}).insert()
		frappe.db.delete("Driver Daily Log", {"driver": driver})
		log = frappe.get_doc({"doctype": "Driver Daily Log", "driver": driver, "vehicle": "KFUEL 001F", "odometer_start": 500,
							  "fuel_level": "Half", "fit_to_drive": 1, "trip": "Other Trip"}).insert()
		for row in log.checklist:
			row.ok = 1
		log.save()
		with patch(NOTIFY):
			log.submit()
		log.fuel_added_litres = 20
		log.fuel_cost = cost
		with patch(NOTIFY):
			log.save()  # fuel is entered after the trip
		log.reload()
		return log

	def test_fuel_expense_raised(self):
		from school_erp.api.expenses import decide

		frappe.db.set_single_value("School Settings", "expense_single_approval_limit", 100000)
		log = self._driver_log(4000)
		self.assertTrue(log.fuel_expense)
		exp = frappe.get_doc("School Expense", log.fuel_expense)
		self.assertEqual((exp.expense_category, flt(exp.amount), exp.status), ("Fuel", 4000, "Pending Approval"))
		self.assertIn(log.name, exp.description)
		self.assertEqual(decide(exp.name, "Approved"), "Approved")
		exp.reload()
		fuel_account = frappe.db.get_value("Expense Category", "Fuel", "expense_account")
		self.assertEqual(self.lines(exp.journal_entry).get(fuel_account), 4000)

	def test_fuel_log_cancel(self):
		log = self._driver_log(1500)
		exp = log.fuel_expense
		self.assertTrue(exp)
		log.cancel()
		self.assertFalse(frappe.db.exists("School Expense", exp))
