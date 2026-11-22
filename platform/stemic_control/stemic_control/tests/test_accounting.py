"""Stemic's books in ERPNext: subscription invoices, payments and agents' commission become Sales Invoices, Payment
Entries and Journal Entries, with the general ledger checked line by line. Needs ERPNext on the site; skipped without.
bench --site <site with erpnext and stemic_control> run-tests --module stemic_control.tests.test_accounting"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import accounting, api, billing, setup_check

COMPANY = "_Stemic Books Test"


def _company():
    """A company set up the way a real one is (ERPNext's setup wizard: chart of accounts, groups), with fiscal years
    for this year and next (subscription periods run ahead of today)."""
    year = getdate(nowdate()).year
    if not frappe.db.exists("Company", COMPANY):
        from erpnext.setup.setup_wizard.setup_wizard import setup_complete

        setup_complete(frappe._dict({"language": "English", "country": "Kenya", "currency": "KES", "company_name": COMPANY,
                                     "company_abbr": "_SBT", "chart_of_accounts": "Standard", "domain": "Services",
                                     "fy_start_date": f"{year}-01-01", "fy_end_date": f"{year}-12-31"}))
        frappe.db.set_single_value("System Settings", "setup_complete", 1)
    for y in (year, year + 1):
        if not frappe.db.exists("Fiscal Year", {"year_start_date": f"{y}-01-01"}):
            frappe.get_doc({"doctype": "Fiscal Year", "year": f"{y}", "year_start_date": f"{y}-01-01",
                            "year_end_date": f"{y}-12-31"}).insert()
    frappe.db.commit()


class TestAccounting(TestCase):
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
        self.posting(True)
        self.vat("Standard Rated")
        user = f"agent-{frappe.generate_hash(length=6)}@books.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Agent", "send_welcome_email": 0,
                        "roles": [{"role": "Stemic Agent"}]}).insert(ignore_permissions=True)
        self.agent = frappe.get_doc({"doctype": "SaaS Agent", "agent_name": "Books Agent " + frappe.generate_hash(length=4),
                                     "user": user, "status": "Active", "commission_rate": 10}).insert().name
        slug = "books-" + frappe.generate_hash(length=6).lower()
        self.tenant = api.register_tenant("Books Academy", slug, "head@books.test", self.agent)
        self.plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Books " + frappe.generate_hash(length=5), "enabled": 1,
                                    "monthly_price": 5000, "student_limit": 400, "modules": "[]"}).insert().name
        self.sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": self.plan, "agent": self.agent,
                                   "starts_on": nowdate(), "ends_on": add_days(nowdate(), 10)}).insert().name

    def tearDown(self):
        self._conf.stop()
        frappe.set_user("Administrator")
        frappe.db.rollback()
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
        frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")

    def posting(self, on):
        """Posting is compulsory once a company is chosen: 'off' means no company."""
        frappe.db.set_single_value("Stemic Settings", {"post_to_accounts": int(on), "accounting_company": COMPANY if on else None})
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

    def vat(self, treatment):
        frappe.db.set_single_value("Stemic Tax Settings", {"tax_treatment": treatment, "vat_rate": 16})
        frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")

    def acc(self, key):
        return accounting.account(COMPANY, key)

    def gl(self, voucher_type, voucher_no):
        rows = frappe.get_all("GL Entry", filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
                              fields=["account", "debit", "credit", "party"])
        out = {}
        for r in rows:
            d, c = out.get(r.account, (0, 0))
            out[r.account] = (flt(d + r.debit, 2), flt(c + r.credit, 2))
        return out

    def pay(self, invoice, amount, mode="M-Pesa"):
        return billing.record_payment(invoice, amount, mode, "Q" + frappe.generate_hash(length=8).upper())

    # ------------------------------------------------------------------
    def test_setup_is_idempotent(self):
        first = accounting.setup_accounts()
        again = accounting.setup_accounts()
        self.assertEqual(first, again)
        self.assertEqual(frappe.db.get_value("Account", first["vat"], "account_type"), "Tax")
        self.assertEqual(frappe.db.get_value("Account", first["commission_payable"], "account_type"), "Payable")
        self.assertEqual(frappe.db.get_value("Account", first["plans"][self.plan], "root_type"), "Income")
        mpesa = frappe.get_doc("Mode of Payment", "M-Pesa")
        self.assertEqual([r.default_account for r in mpesa.accounts if r.company == COMPANY], [first["mpesa"]])

    def test_invoice_payment_and_commission_reach_the_ledger(self):
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=6))
        self.assertTrue(inv.sales_invoice)
        si = frappe.get_doc("Sales Invoice", inv.sales_invoice)
        self.assertEqual((si.docstatus, flt(si.grand_total), si.customer), (1, 30000, frappe.db.get_value("SaaS Tenant", self.tenant, "erp_customer")))
        self.assertEqual(frappe.db.get_value("Customer", si.customer, "customer_name"), "Books Academy")
        item = si.items[0]
        self.assertEqual((item.qty, getdate(item.service_start_date), getdate(item.service_end_date)),
                         (6, getdate(inv.period_start), getdate(inv.period_end)))
        # VAT is inside the price: 30,000 = 25,862.07 + 4,137.93 (16/116), and the income waits in Deferred
        ledger = self.gl("Sales Invoice", si.name)
        self.assertEqual(ledger[si.debit_to], (30000, 0))
        self.assertEqual(ledger[self.acc("vat")], (0, 4137.93))
        self.assertEqual(ledger[self.acc("deferred")], (0, 25862.07))
        self.assertEqual(item.income_account, accounting.plan_item(COMPANY, self.plan)[1])

        payment = frappe.get_doc("SaaS Payment", self.pay(inv.name, 30000)["payment"])
        self.assertTrue(payment.payment_entry)
        ledger = self.gl("Payment Entry", payment.payment_entry)
        self.assertEqual(ledger[self.acc("mpesa")], (30000, 0))
        self.assertEqual(ledger[si.debit_to], (0, 30000))
        self.assertEqual(flt(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount")), 0)

        com = frappe.get_doc("SaaS Commission", {"payment": payment.name})
        ledger = self.gl("Journal Entry", com.journal_entry)
        self.assertEqual(ledger[self.acc("commission")], (3000, 0))
        self.assertEqual(ledger[self.acc("commission_payable")], (0, 3000))
        supplier = frappe.db.get_value("SaaS Agent", self.agent, "erp_supplier")
        self.assertEqual(frappe.db.get_value("GL Entry", {"voucher_no": com.journal_entry, "credit": (">", 0)}, "party"), supplier)

        billing.pay_commissions(self.agent, "B2C-BOOKS-1", mode="M-Pesa")
        payout = frappe.db.get_value("SaaS Commission", com.name, "payout_entry")
        ledger = self.gl("Journal Entry", payout)
        self.assertEqual(ledger[self.acc("commission_payable")], (3000, 0))
        self.assertEqual(ledger[self.acc("mpesa")], (0, 3000))

    def test_deferred_income_is_released_month_by_month(self):
        """What ERPNext's monthly job does (Process Deferred Accounting): one month of the period becomes income."""
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=6))
        first_month_end = add_days(add_months(getdate(inv.period_start), 1), -1)
        frappe.get_doc({"doctype": "Process Deferred Accounting", "type": "Income", "company": COMPANY,
                        "start_date": inv.period_start, "end_date": first_month_end, "posting_date": first_month_end}).submit()
        income = accounting.plan_item(COMPANY, self.plan)[1]
        booked = flt(sum(frappe.get_all("GL Entry", filters={"account": income, "is_cancelled": 0},
                                        or_filters={"voucher_no": inv.sales_invoice, "against_voucher": inv.sales_invoice},
                                        pluck="credit")), 2)
        self.assertAlmostEqual(booked, 25862.07 / 6, delta=200)  # about one month's net (by days in the month)

    def test_discount_keeps_the_books_equal_to_the_invoice(self):
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=3, discount_amount=1500))
        si = frappe.get_doc("Sales Invoice", inv.sales_invoice)
        self.assertEqual((flt(inv.total), flt(si.grand_total)), (13500, 13500))
        self.assertEqual(self.gl("Sales Invoice", si.name)[self.acc("vat")], (0, 1862.07))  # 13,500 x 16/116

    def test_cancelling_reverses_the_entries(self):
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=6))
        payment = frappe.get_doc("SaaS Payment", self.pay(inv.name, 30000, mode="Bank Transfer")["payment"])
        self.assertIn(self.acc("bank"), self.gl("Payment Entry", payment.payment_entry))
        com = frappe.db.get_value("SaaS Commission", {"payment": payment.name}, "journal_entry")
        payment.cancel()
        self.assertEqual(frappe.db.get_value("Payment Entry", payment.payment_entry, "docstatus"), 2)
        self.assertEqual(frappe.db.get_value("Journal Entry", com, "docstatus"), 2)
        frappe.get_doc("SaaS Invoice", inv.name).cancel()
        self.assertEqual(frappe.db.get_value("Sales Invoice", inv.sales_invoice, "docstatus"), 2)

    def test_exempt_school_invoice_has_no_vat(self):
        self.vat("Exempt")
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=2))
        ledger = self.gl("Sales Invoice", inv.sales_invoice)
        self.assertNotIn(self.acc("vat"), ledger)
        self.assertEqual(ledger[self.acc("deferred")], (0, 10000))

    def test_posting_is_compulsory_once_a_company_is_chosen(self):
        frappe.db.set_single_value("Stemic Settings", {"post_to_accounts": 0, "accounting_company": COMPANY})  # old switch off
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=1))
        self.assertTrue(inv.sales_invoice)

    def test_post_missing_and_ledger_check(self):
        self.posting(False)  # records made before a company was chosen
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=1))
        payment = self.pay(inv.name, 5000)["payment"]
        self.posting(True)
        names = {u["name"] for u in accounting.ledger_check()["unposted"]}
        self.assertTrue({inv.name, payment} <= names)
        result = accounting.post_missing()
        self.assertIn(inv.name, result["posted"])
        self.assertIn(payment, result["posted"])
        self.assertFalse(result["failed"])
        check = accounting.ledger_check()
        self.assertFalse([u for u in check["unposted"] if u["name"] in (inv.name, payment)])
        self.assertFalse([m for m in check["mismatches"] if m["name"] == inv.name])  # paid in full here and in the books
        self.assertTrue(frappe.db.get_value("SaaS Commission", {"payment": payment}, "journal_entry"))

    def test_nothing_is_posted_when_switched_off(self):
        self.posting(False)
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=1))
        payment = frappe.get_doc("SaaS Payment", self.pay(inv.name, 5000)["payment"])
        self.assertFalse(inv.sales_invoice or payment.payment_entry)
        self.assertFalse(frappe.db.get_value("SaaS Commission", {"payment": payment.name}, "journal_entry"))

    def test_a_foreign_currency_invoice_is_refused(self):
        inv = frappe.get_doc({"doctype": "SaaS Invoice", "tenant": self.tenant, "subscription": self.sub, "issue_date": nowdate(),
                              "period_start": nowdate(), "months": 1, "currency": "USD"}).insert()
        with self.assertRaises(frappe.ValidationError):
            inv.submit()

    def test_setup_check_reports_the_books(self):
        accounting.setup_accounts()
        items = {i["label"]: i for i in setup_check.status()["items"] if i["area"] == "Accounts"}
        self.assertTrue(items["Company"]["ok"])
        self.assertTrue(items["Fiscal year"]["ok"])
        self.assertTrue(items["Accounts"]["ok"])
