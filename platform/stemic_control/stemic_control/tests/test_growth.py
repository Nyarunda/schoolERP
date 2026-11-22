"""Growth & Health figures on the Control Center overview (specs/features/growth-kpis).
bench --site <site> run-tests --module stemic_control.tests.test_growth"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, nowdate

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, billing, dashboard


class TestGrowth(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
		self._conf.start()
		frappe.db.set_single_value("Stemic Settings", "accounting_company", None)  # no books needed for the figures
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
		self.before = dashboard.growth()
		slug = "gr-" + frappe.generate_hash(length=6).lower()
		self.tenant = api.register_tenant("Growth Academy", slug, "head@growth.test")
		frappe.db.set_value("SaaS Tenant", self.tenant, "county", "Kisii")
		self.plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Gr " + frappe.generate_hash(length=5), "enabled": 1,
									"monthly_price": 4000, "student_limit": 400, "modules": "[]"}).insert().name
		self.sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": self.plan,
								   "starts_on": add_days(nowdate(), -5), "ends_on": add_days(nowdate(), 25)}).insert().name
		frappe.db.set_value("SaaS Subscription", self.sub, "status", "Active")
		self.inv = billing.create_invoice(self.sub, months=1, period_start=add_days(nowdate(), -5))
		billing.record_payment(self.inv, 3000, "M-Pesa", "Q" + frappe.generate_hash(length=8).upper())

	def tearDown(self):
		self._conf.stop()
		frappe.db.rollback()
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

	def test_kpis_move_with_a_new_paying_school(self):
		g = dashboard.growth()
		k, b = g["kpis"], self.before["kpis"]
		self.assertEqual(k["paying"], b["paying"] + 1)
		self.assertEqual(flt(k["mrr"] - b["mrr"]), 4000)
		self.assertEqual(k["arr"], flt(k["mrr"] * 12, 2))
		self.assertEqual(flt(g["mrr_trend"][-1] - self.before["mrr_trend"][-1]), 4000)  # this month's invoice covers today
		self.assertEqual(flt(g["collected"][-1] - self.before["collected"][-1]), 3000)
		self.assertEqual(g["new_schools"][-1], self.before["new_schools"][-1] + 1)
		self.assertEqual(len(g["months"]), 12)

	def test_ageing_and_owed(self):
		g = dashboard.growth()
		self.assertEqual([a["label"] for a in g["ageing"]], [a[0] for a in dashboard.AGEING])
		self.assertAlmostEqual(flt(g["kpis"]["owed"] - self.before["kpis"]["owed"]), 1000, places=2)
		due = frappe.db.get_value("SaaS Invoice", self.inv, "due_date")
		frappe.db.set_value("SaaS Invoice", self.inv, {"due_date": add_days(nowdate(), -45), "status": "Overdue"})
		g = dashboard.growth()
		bucket = {a["label"]: a["amount"] for a in g["ageing"]}
		self.assertGreaterEqual(bucket["31-60 days"], 1000)
		frappe.db.set_value("SaaS Invoice", self.inv, "due_date", due)

	def test_counties_plans_and_churn(self):
		g = dashboard.growth()
		self.assertIn("Kisii", [c.county for c in g["counties"]])
		self.assertIn(self.plan, [p.name for p in g["plans"]])
		frappe.db.set_value("SaaS Subscription", self.sub, "status", "Cancelled")
		g = dashboard.growth()
		self.assertEqual(g["kpis"]["lost_30"], self.before["kpis"]["lost_30"] + 1)
		self.assertGreater(g["kpis"]["churn_pct"], 0)

	def test_costs_count_in_cash_vs_costs(self):
		exp = frappe.get_doc({"doctype": "Stemic Expense", "category": self.category(), "paid_to": "Hetzner", "description": "Server",
							  "amount": 1500, "mode": "M-Pesa"}).insert()
		frappe.db.set_value("Stemic Expense", exp.name, "docstatus", 1)
		g = dashboard.growth()
		self.assertEqual(flt(g["costs"][-1] - self.before["costs"][-1]), 1500)
		self.assertEqual(g["net"][-1], flt(g["collected"][-1] - g["commission"][-1] - g["costs"][-1], 2))

	def category(self):
		name = "Growth Test Costs"
		if not frappe.db.exists("Stemic Expense Category", name):
			frappe.get_doc({"doctype": "Stemic Expense Category", "category_name": name, "enabled": 1}).insert()
		return name

	def test_admin_only(self):
		email = "not.admin@growth.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Not Admin", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertRaises(frappe.PermissionError, dashboard.growth)
