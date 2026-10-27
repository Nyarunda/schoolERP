"""Subscription billing against a database: invoices, payments, the subscription they extend, agents' commission,
the daily job, who sees what, settings and the setup check.
bench --site <site> run-tests --module stemic_control.tests.test_subscription_billing"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, billing, config, setup_check


class TestSubscriptionBilling(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
        self._conf.start()
        user = f"agent-{frappe.generate_hash(length=6)}@stemic.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Agent", "send_welcome_email": 0,
                        "roles": [{"role": "Stemic Agent"}]}).insert(ignore_permissions=True)
        self.agent_user = user
        self.agent = frappe.get_doc({"doctype": "SaaS Agent", "agent_name": "Billing Agent", "user": user, "status": "Active",
                                     "commission_rate": 10}).insert().name
        slug = "bill-" + frappe.generate_hash(length=6).lower()
        self.tenant = api.register_tenant("Billing Academy", slug, "head@bill.test", self.agent)
        self.plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Bill " + frappe.generate_hash(length=5), "enabled": 1,
                                    "monthly_price": 5000, "student_limit": 400, "modules": "[]"}).insert().name
        self.sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": self.plan, "agent": self.agent,
                                   "starts_on": nowdate(), "ends_on": add_days(nowdate(), 10)}).insert().name

    def tearDown(self):
        self._conf.stop()
        frappe.set_user("Administrator")

    def daily(self):
        """Run the scheduler job without its commit, so the test's records still roll back."""
        with patch.object(frappe.db, "commit"):
            billing.daily()

    def pay(self, invoice, amount, ref=None, mode="M-Pesa"):
        return billing.record_payment(invoice, amount, mode, ref or ("Q" + frappe.generate_hash(length=8).upper()))

    # ------------------------------------------------------------------ invoices and payments
    def test_invoice_payment_extends_the_subscription_and_pays_commission(self):
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=12))
        self.assertEqual((flt(inv.total), inv.status, inv.months), (60000, "Unpaid", 12))
        self.assertEqual(getdate(inv.period_start), getdate(add_days(nowdate(), 11)))  # continues from the current end
        self.assertEqual(getdate(inv.period_end), getdate(add_days(add_months(add_days(nowdate(), 11), 12), -1)))
        self.assertRaises(frappe.ValidationError, billing.create_invoice, self.sub)  # one open invoice at a time

        first = self.pay(inv.name, 20000)
        self.assertEqual((first["invoice_status"], flt(first["outstanding"])), ("Partly Paid", 40000))
        self.assertRaises(frappe.ValidationError, self.pay, inv.name, 50000)  # more than is owed
        ref = "QPAID" + frappe.generate_hash(length=4).upper()
        last = self.pay(inv.name, 40000, ref)
        self.assertEqual(last["invoice_status"], "Paid")
        self.assertRaises(frappe.ValidationError, self.pay, inv.name, 1, ref)  # nothing owed, and the ref is used

        sub = frappe.get_doc("SaaS Subscription", self.sub)
        self.assertEqual((sub.status, getdate(sub.ends_on), sub.external_payment_ref), ("Active", getdate(inv.period_end), ref))
        commission = frappe.get_all("SaaS Commission", filters={"invoice": inv.name}, fields=["amount", "status"])
        self.assertEqual(sorted(flt(c.amount) for c in commission), [2000, 4000])  # 10% of each payment
        self.assertEqual(billing.pay_commissions(self.agent, "B2C-PAYOUT-1")["paid"], 2)
        self.assertEqual(set(frappe.get_all("SaaS Commission", filters={"invoice": inv.name}, pluck="status")), {"Paid"})

    def test_cancelling_a_payment_reverses_it(self):
        inv = billing.create_invoice(self.sub, months=6)
        payment = self.pay(inv, 30000)["payment"]
        self.assertEqual(frappe.db.get_value("SaaS Invoice", inv, "status"), "Paid")
        frappe.get_doc("SaaS Payment", payment).cancel()
        self.assertEqual(frappe.db.get_value("SaaS Invoice", inv, "status"), "Unpaid")
        self.assertEqual(getdate(frappe.db.get_value("SaaS Subscription", self.sub, "ends_on")), getdate(add_days(nowdate(), 10)))
        self.assertEqual(frappe.db.get_value("SaaS Commission", {"payment": payment}, "status"), "Cancelled")

        paid_out = self.pay(inv, 30000)["payment"]
        billing.pay_commissions(self.agent, "PAYOUT-2")
        self.assertRaises(frappe.ValidationError, frappe.get_doc("SaaS Payment", paid_out).cancel)  # agent already paid

    def test_ledger_check_finds_invoices_that_disagree_with_their_payments(self):
        """Found by the daily job and the Setup Check, without anyone opening the invoice."""
        inv = billing.create_invoice(self.sub, months=6)  # 30,000
        self.pay(inv, 10000)
        found = lambda: {m["invoice"]: m["problem"] for m in billing.ledger_mismatches(limit=500)}
        self.assertNotIn(inv, found())  # paid and outstanding agree with the ledger

        frappe.db.set_value("SaaS Invoice", inv, "paid_amount", 15000)  # e.g. an edit outside the billing code
        self.assertIn("its payments come to 10,000.00", found()[inv])
        frappe.db.set_value("SaaS Invoice", inv, {"paid_amount": 10000, "outstanding": 30000})
        self.assertIn(inv, found())
        frappe.db.set_value("SaaS Invoice", inv, {"outstanding": 20000, "docstatus": 2})  # cancelled under a live payment
        self.assertIn("still submitted", found()[inv])
        frappe.db.set_value("SaaS Invoice", inv, {"docstatus": 1, "total": 5000})
        self.assertIn("exceed the total", found()[inv])

        with patch.object(frappe.db, "commit"):
            self.assertGreaterEqual(billing.check_ledger(), 1)
        log = frappe.get_all("Error Log", filters={"method": ("like", "Billing ledger:%")}, fields=["error"], order_by="creation desc", limit=1)
        self.assertIn(inv, log[0].error)
        item = next(i for i in setup_check._business() if i["label"] == "Invoices match their payments")
        self.assertFalse(item["ok"])

    def test_invoice_summary_counts_only_submitted_payments(self):
        """What the invoice card shows: the ledger, with cancelled payments listed but not counted, and drafts left out."""
        inv = billing.create_invoice(self.sub, months=6)  # 30,000
        cancelled = self.pay(inv, 10000)["payment"]
        kept = self.pay(inv, 5000)["payment"]
        frappe.get_doc("SaaS Payment", cancelled).cancel()
        frappe.get_doc({"doctype": "SaaS Payment", "invoice": inv, "amount": 1000, "mode": "M-Pesa",
                        "reference": "QDRAFT" + frappe.generate_hash(length=4).upper(), "payment_date": nowdate()}).insert()

        summary = billing.invoice_summary(inv)
        stored = frappe.db.get_value("SaaS Invoice", inv, ["paid_amount", "outstanding"], as_dict=True)
        self.assertEqual((summary["total"], summary["paid"], summary["outstanding"], summary["paid_percent"]), (30000, 5000, 25000, 16))
        self.assertEqual((summary["paid"], summary["outstanding"]), (flt(stored.paid_amount), flt(stored.outstanding)))
        self.assertTrue(summary["matches_invoice"])
        listed = {p["name"]: p["cancelled"] for p in summary["payments"]}
        self.assertEqual(listed, {kept: False, cancelled: True})  # the draft is not on the card

        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, billing.invoice_summary, inv)

    def test_first_payment_only_commission(self):
        with patch.object(billing, "settings", lambda: frappe._dict(currency="KES", billing_months=12, payment_terms_days=14,
                                                                   renewal_notice_days=30, commission_basis="First payment only")):
            self.pay(billing.create_invoice(self.sub, months=1), 5000)
            self.pay(billing.create_invoice(self.sub, months=1), 5000)
        self.assertEqual(frappe.db.count("SaaS Commission", {"tenant": self.tenant, "status": "Due"}), 1)

    def test_renew_goes_through_an_invoice_and_payment(self):
        out = api.renew_subscription(self.sub, 3, "QRENEW" + frappe.generate_hash(length=4).upper(), "Bank Transfer")
        self.assertEqual(frappe.db.get_value("SaaS Invoice", out["invoice"], ["status", "months"]), ("Paid", 3))
        self.assertEqual(frappe.db.get_value("SaaS Payment", out["payment"], "mode"), "Bank Transfer")

    def test_manual_invoice_submit_rechecks_existing_unpaid_invoice(self):
        existing = billing.create_invoice(self.sub, months=1)
        self.assertTrue(existing)
        other = frappe.get_doc({
            "doctype": "SaaS Invoice", "tenant": self.tenant,
            "subscription": self.sub, "issue_date": nowdate(),
            "period_start": add_days(nowdate(), 11), "months": 1,
        }).insert()
        self.assertRaises(frappe.ValidationError, other.submit)
        self.assertEqual(frappe.db.get_value("SaaS Invoice", other.name, "docstatus"), 0)

    def test_whitespace_payment_reference_rejected(self):
        invoice = billing.create_invoice(self.sub, months=1)
        payment = frappe.get_doc({
            "doctype": "SaaS Payment", "invoice": invoice, "amount": 1000,
            "mode": "M-Pesa", "reference": "   ", "payment_date": nowdate(),
        })
        self.assertRaises(frappe.ValidationError, payment.insert)

    def test_stale_draft_cannot_overpay_after_another_receipt(self):
        invoice = billing.create_invoice(self.sub, months=1)
        stale = frappe.get_doc({
            "doctype": "SaaS Payment", "invoice": invoice, "amount": 4000,
            "mode": "M-Pesa", "reference": "STALE-" + frappe.generate_hash(length=10),
            "payment_date": nowdate(),
        }).insert()
        self.pay(invoice, 4000)
        # The draft passed initial validation when the invoice was unpaid.
        # before_submit must lock and recalculate the actual ledger balance.
        self.assertRaises(frappe.ValidationError, stale.submit)
        self.assertEqual(frappe.db.get_value("SaaS Payment", stale.name, "docstatus"), 0)
        self.assertEqual(flt(frappe.db.get_value("SaaS Invoice", invoice, "outstanding")), 1000)

    def test_payment_mode_reference_identity_unique_at_database_level(self):
        first = billing.create_invoice(self.sub, months=1)
        ref = "DUP-" + frappe.generate_hash(length=12).upper()
        self.pay(first, 1000, ref=ref)
        # Record with same bank/M-Pesa reference cannot be reused, even on another invoice.
        other = api.register_tenant("Second School", "dup-" + frappe.generate_hash(length=6).lower(),
                                    "second@billing.test")
        second_sub = frappe.get_doc({
            "doctype": "SaaS Subscription", "tenant": other, "plan": self.plan,
            "starts_on": nowdate(),
        }).insert().name
        second = billing.create_invoice(second_sub, months=1)
        duplicate = frappe.get_doc({
            "doctype": "SaaS Payment", "invoice": second, "amount": 1000,
            "mode": "M-Pesa", "reference": ref, "payment_date": nowdate(),
        })
        self.assertRaises(frappe.ValidationError, duplicate.insert)

    def test_cancelled_payment_releases_its_reference(self):
        """A payment recorded against the wrong invoice is cancelled and the same M-Pesa code recorded again."""
        wrong = billing.create_invoice(self.sub, months=1)
        ref = "QFIX" + frappe.generate_hash(length=8).upper()
        payment = self.pay(wrong, 1000, ref=ref)["payment"]
        frappe.get_doc("SaaS Payment", payment).cancel()
        self.assertIsNone(frappe.db.get_value("SaaS Payment", payment, "reference_key"))
        again = self.pay(wrong, 1000, ref=ref)["payment"]  # not blocked by the cancelled payment's key
        self.assertTrue(frappe.db.get_value("SaaS Payment", again, "reference_key"))

    def test_backfill_gives_old_payments_their_key_and_reports_duplicates(self):
        """Payments recorded before the unique key existed: keyed by the migration, duplicates left for a person."""
        from stemic_control.patches.backfill_payment_reference_keys import execute

        a, b = billing.create_invoice(self.sub, months=1), None
        first = self.pay(a, 1000, ref="QOLD" + frappe.generate_hash(length=6).upper())["payment"]
        second = self.pay(a, 1000)["payment"]
        ref = frappe.db.get_value("SaaS Payment", first, "reference")
        # as they were before the key: no key, and (in old data) the same reference twice
        frappe.db.set_value("SaaS Payment", first, "reference_key", None)
        frappe.db.set_value("SaaS Payment", second, {"reference_key": None, "reference": ref})
        execute()
        self.assertEqual(frappe.db.get_value("SaaS Payment", first, "reference_key"), billing.reference_key("M-Pesa", ref))
        self.assertIsNone(frappe.db.get_value("SaaS Payment", second, "reference_key"))
        self.assertTrue(frappe.db.exists("Error Log", {"method": "Payments left without a unique reference key"}))

    # ------------------------------------------------------------------ daily job
    def test_daily_marks_overdue_and_raises_renewals(self):
        inv = billing.create_invoice(self.sub, months=1)
        frappe.db.set_value("SaaS Invoice", inv, {"due_date": add_days(nowdate(), -1), "issue_date": add_days(nowdate(), -20)})
        frappe.db.set_value("SaaS Subscription", self.sub, {"status": "Active", "starts_on": add_days(nowdate(), -60),
                                                          "ends_on": add_days(nowdate(), -2)})
        self.daily()
        self.assertEqual(frappe.db.get_value("SaaS Invoice", inv, "status"), "Overdue")
        self.assertEqual(frappe.db.get_value("SaaS Subscription", self.sub, "status"), "Past Due")

        frappe.get_doc("SaaS Invoice", inv).cancel()
        frappe.db.set_value("SaaS Subscription", self.sub, {"status": "Active", "ends_on": add_days(nowdate(), 5)})
        self.daily()
        renewal = billing.open_invoice(self.sub)
        self.assertTrue(renewal)
        self.assertEqual(getdate(frappe.db.get_value("SaaS Invoice", renewal, "period_start")), getdate(add_days(nowdate(), 6)))

    # ------------------------------------------------------------------ access
    def test_agents_see_only_their_own_billing(self):
        mine = billing.create_invoice(self.sub, months=1)
        self.pay(mine, 5000)
        other_tenant = api.register_tenant("Other School", "oth-" + frappe.generate_hash(length=6).lower(), "head@oth.test")
        other_sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": other_tenant, "plan": self.plan,
                                    "starts_on": nowdate()}).insert().name
        other = billing.create_invoice(other_sub, months=1)

        frappe.set_user(self.agent_user)
        invoices = set(frappe.get_list("SaaS Invoice", pluck="name"))
        self.assertIn(mine, invoices)
        self.assertNotIn(other, invoices)
        self.assertTrue(frappe.get_list("SaaS Commission", pluck="name"))
        self.assertTrue(all(p for p in frappe.get_list("SaaS Payment", pluck="invoice") if p == mine))
        self.assertRaises(frappe.PermissionError, billing.create_invoice, self.sub)
        from stemic_control.stemic_control.report.agent_commission_statement.agent_commission_statement import execute

        _c, rows, *_ = execute({"from_date": add_days(nowdate(), -1), "to_date": nowdate()})
        self.assertTrue(rows and all(r.agent == self.agent for r in rows))

    def test_reports_add_up(self):
        inv = billing.create_invoice(self.sub, months=2)
        self.pay(inv, 4000)
        from stemic_control.stemic_control.report.saas_receivables.saas_receivables import execute as receivables
        from stemic_control.stemic_control.report.saas_revenue.saas_revenue import execute as revenue

        _c, months, *_ = revenue({"from_date": nowdate(), "to_date": nowdate(), "plan": self.plan})
        self.assertEqual((flt(months[-1].invoiced), flt(months[-1].collected), flt(months[-1].commission)), (10000, 4000, 400))
        _c, owing, *_ = receivables({"as_on": nowdate()})
        self.assertEqual(flt(next(r for r in owing if r.tenant == self.tenant).outstanding), 6000)

    # ------------------------------------------------------------------ settings and setup
    def test_site_config_wins_then_settings_then_default(self):
        settings = frappe.get_doc("Stemic Settings")
        settings.site_domain = "schools.example.org"
        settings.save()
        with patch.dict(frappe.local.conf, {"stemic_site_domain": None}):
            self.assertEqual((config.get("stemic_site_domain"), config.source("stemic_site_domain")), ("schools.example.org", "settings"))
        with patch.dict(frappe.local.conf, {"stemic_site_domain": "server.local"}):
            self.assertEqual((config.get("stemic_site_domain"), config.source("stemic_site_domain")), ("server.local", "site_config"))
        settings.site_domain = None
        settings.save()
        with patch.dict(frappe.local.conf, {"stemic_site_domain": None}):
            self.assertEqual(config.get("stemic_site_domain"), "localhost")

    def test_setup_check_reports_without_revealing_secrets(self):
        with patch.dict(frappe.local.conf, {"stemic_db_root_password": "never-show-this-9271", "stemic_local_provisioner": 1}):
            result = setup_check.status()
        self.assertTrue(result["items"])
        self.assertNotIn("never-show-this-9271", frappe.as_json(result))
        root = next(i for i in result["items"] if i["label"] == "Database root access")
        self.assertIs(root["ok"], False)  # a wrong password is reported, not shown
        frappe.set_user(self.agent_user)
        self.assertRaises(frappe.PermissionError, setup_check.status)
