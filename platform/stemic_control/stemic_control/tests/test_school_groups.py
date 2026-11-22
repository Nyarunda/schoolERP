"""Schools with several branches, each its own site, grouped in the Control Center (specs/features/school-groups).
Needs ERPNext for the cost-center tests; bench --site <site> run-tests --module stemic_control.tests.test_school_groups"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, nowdate

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import accounting, api, billing, communications, groups
from stemic_control.tests.test_accounting import COMPANY, _company


class TestSchoolGroups(TestCase):
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
		accounting.setup_accounts()
		tag = frappe.generate_hash(length=5)
		self.group = frappe.get_doc({"doctype": "SaaS School Group", "group_name": f"Greenhills {tag}", "billing_mode": groups.COMBINED,
									 "billing_email": f"accounts@greenhills-{tag}.co.ke"}).insert().name
		self.plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Grp " + tag, "enabled": 1, "monthly_price": 3000,
									"student_limit": 400, "modules": "[]"}).insert().name
		self.branches, self.invoices = [], []
		for i, campus in enumerate(("Kisii Campus", "Nyamira Campus")):
			slug = f"gh{i}-" + frappe.generate_hash(length=5).lower()
			t = api.register_tenant(f"Greenhills {campus}", slug, f"head{i}@{slug}.test")
			frappe.get_doc("SaaS Tenant", t).update({"school_group": self.group, "branch_name": campus}).save()
			sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": t, "plan": self.plan, "starts_on": add_days(nowdate(), -i),
								  "ends_on": add_days(nowdate(), 10)}).insert().name
			self.branches.append(t)
			self.invoices.append(billing.create_invoice(sub, months=1))

	def tearDown(self):
		self._conf.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

	def test_branch_cost_centers_under_the_group(self):
		group_cc = frappe.db.get_value("SaaS School Group", self.group, "cost_center")
		self.assertTrue(group_cc and frappe.db.get_value("Cost Center", group_cc, "is_group"))
		for t in self.branches:
			cc = frappe.db.get_value("SaaS Tenant", t, "cost_center")
			self.assertEqual(frappe.db.get_value("Cost Center", cc, "parent_cost_center"), group_cc)
		single = api.register_tenant("Single Academy", "single-" + frappe.generate_hash(length=5).lower(), "h@single.test")
		cc = groups.cost_center(single)
		self.assertEqual(frappe.db.get_value("Cost Center", frappe.db.get_value("Cost Center", cc, "parent_cost_center"), "cost_center_name"),
						 groups.SCHOOLS_GROUP)

	def test_invoice_and_payment_post_with_the_branch_cost_center(self):
		inv = frappe.get_doc("SaaS Invoice", self.invoices[0])
		cc = frappe.db.get_value("SaaS Tenant", self.branches[0], "cost_center")
		income = frappe.get_all("GL Entry", filters={"voucher_no": inv.sales_invoice, "is_cancelled": 0, "credit": (">", 0)},
								fields=["cost_center", "account"])
		self.assertTrue(income and all(r.cost_center == cc for r in income if "Debtors" not in r.account))
		pay = billing.record_payment(inv.name, 1000, "M-Pesa", "Q" + frappe.generate_hash(length=8).upper())["payment"]
		pe = frappe.db.get_value("SaaS Payment", pay, "payment_entry")
		self.assertEqual(frappe.db.get_value("Payment Entry", pe, "cost_center"), cc)

	def test_moving_a_school_into_a_group_moves_its_cost_center(self):
		t = api.register_tenant("Joining Academy", "join-" + frappe.generate_hash(length=5).lower(), "h@join.test")
		cc = groups.cost_center(t)
		frappe.get_doc("SaaS Tenant", t).update({"school_group": self.group, "branch_name": "Keroka"}).save()
		self.assertEqual(frappe.db.get_value("Cost Center", cc, "parent_cost_center"),
						 frappe.db.get_value("SaaS School Group", self.group, "cost_center"))

	def test_combined_billing_emails_go_to_head_office(self):
		head = frappe.db.get_value("SaaS School Group", self.group, "billing_email")
		self.assertEqual(groups.billing_email(self.branches[0], "Invoice Issued"), head)
		self.assertIsNone(groups.billing_email(self.branches[0], "License Issued"))  # not a billing message
		with patch.object(frappe, "sendmail") as mail, patch.object(communications, "wanted", return_value=True):
			communications.deliver(self.branches[0], "Invoice Issued", ("SaaS Invoice", self.invoices[0]), email=("Invoice", "<p>x</p>"))
		self.assertEqual(mail.call_args.kwargs["recipients"], [head])
		frappe.db.set_value("SaaS School Group", self.group, "billing_mode", "Each branch billed separately")
		self.assertIsNone(groups.billing_email(self.branches[0], "Invoice Issued"))

	def test_statement_and_group_payment_oldest_first(self):
		overview = groups.group_overview(self.group)
		self.assertEqual(len(overview["branches"]), 2)
		self.assertEqual(overview["owed"], 6000)
		with patch.object(frappe, "sendmail") as mail:
			r = groups.email_statement(self.group)
		self.assertEqual((r["invoices"], r["total"]), (2, 6000))
		self.assertEqual(mail.call_args.kwargs["recipients"], [overview["billing_email"]])
		out = groups.record_group_payment(self.group, 4000, "M-Pesa", "QGROUP1234")
		self.assertEqual([a["amount"] for a in out["allocated"]], [3000, 1000])
		refs = [frappe.db.get_value("SaaS Payment", p, "reference") for p in out["payments"]]
		self.assertEqual(refs, ["QGROUP1234/1", "QGROUP1234/2"])
		self.assertEqual(groups.group_overview(self.group)["owed"], 2000)
		self.assertRaises(frappe.ValidationError, groups.record_group_payment, self.group, 5000, "M-Pesa", "QTOOMUCH1")

	def test_admin_only(self):
		email = "not.admin@groups.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Not Admin", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		for call in (lambda: groups.group_overview(self.group), lambda: groups.email_statement(self.group),
					 lambda: groups.record_group_payment(self.group, 1, "M-Pesa", "X")):
			self.assertRaises(frappe.PermissionError, call)
