"""Onboard a School (wizard.py), the automation around it (licences, trials, the school's subscription link) and the
Overview page's figures. bench --site <site> run-tests --module stemic_control.tests.test_wizard"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_bench_path, nowdate

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import billing, communications, dashboard, licensing, provisioner, wizard
from stemic_control.tests.helpers import plan, remove_school

CONF = {"stemic_platform_domain": "stemic.test", "stemic_site_domain": "localhost",
        "stemic_provision_environment": "development", "stemic_provision_allowed_benches": [get_bench_path()]}


class TestSlug(TestCase):
    def test_suggestion_drops_generic_words(self):
        self.assertEqual(wizard.suggest_slug("St. Teresa's Girls High School"), "st-teresas")
        self.assertEqual(wizard.suggest_slug("Mogonga PAG Secondary School"), "mogonga-pag")
        self.assertEqual(wizard.suggest_slug("Greenhill Academy"), "greenhill")
        self.assertEqual(wizard.suggest_slug("The Academy"), "the-academy")  # only generic words: keep them
        self.assertEqual(wizard.suggest_slug("2nd Avenue School"), "s-2nd-avenue")  # must start with a letter

    def test_reserved_and_taken(self):
        frappe.set_user("Administrator")
        self.assertFalse(wizard.check_slug("admin")["ok"])
        self.assertFalse(wizard.check_slug("A b")["ok"])
        self.assertTrue(wizard.check_slug(school_name="Brand New Wizard School")["ok"])


class TestOnboardSchool(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._enqueue = patch.object(provisioner, "enqueue")
        self._enqueue.start()
        self.slug = "wiz-" + frappe.generate_hash(length=6).lower()

    def tearDown(self):
        self._enqueue.stop()
        self._conf.stop()
        remove_school(self.slug)

    def onboard(self, **kw):
        args = {"school_name": "Wizard School", "admin_email": "head@wizard.test", "plan": plan(), "slug": self.slug, **kw}
        return wizard.onboard_school(**args)

    def test_free_trial_built_straight_away(self):
        r = self.onboard(start="Free trial", trial_days=14, when="build")
        self.assertEqual(r["status"], "Pending")
        self.assertTrue(r["job"])
        self.assertFalse(r["warnings"])
        sub = frappe.get_doc("SaaS Subscription", r["subscription"])
        self.assertEqual((sub.status, sub.billing_exception), ("Trial", "Free Trial"))
        self.assertEqual(str(sub.ends_on), str(add_days(nowdate(), 13)))
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "subscription"), sub.name)
        self.assertEqual(frappe.db.get_value("SaaS Domain", r["host"], "status"), "Verified")
        self.assertTrue(frappe.db.get_value("SaaS Tenant", self.slug, "approved_on"))

    def test_paid_start_records_invoice_and_payment(self):
        r = self.onboard(start="Paid", months=3, payment_ref="WIZ" + frappe.generate_hash(length=6).upper(), when="build")
        self.assertEqual(frappe.db.get_value("SaaS Invoice", r["invoice"], "status"), "Paid")
        self.assertEqual(frappe.db.get_value("SaaS Subscription", r["subscription"], "status"), "Active")
        self.assertTrue(r["job"])

    def test_part_payment_is_approved_but_not_built(self):
        r = self.onboard(start="Paid", months=3, amount=500, payment_ref="WIZ" + frappe.generate_hash(length=6).upper())
        self.assertEqual(frappe.db.get_value("SaaS Invoice", r["invoice"], "status"), "Partly Paid")
        self.assertIsNone(r["job"])
        self.assertEqual(r["status"], "Approved")
        self.assertTrue(any("Part payment" in w for w in r["warnings"]))

    def test_paid_needs_a_reference(self):
        self.assertRaises(frappe.ValidationError, self.onboard, start="Paid")

    def test_waits_for_another_admin_or_stays_draft(self):
        self.assertEqual(self.onboard(start="Internal / Demo", when="approval")["status"], "Pending Approval")

    def test_draft(self):
        r = self.onboard(start="Internal / Demo", when="draft")
        self.assertEqual(r["status"], "Draft")
        self.assertEqual(frappe.db.get_value("SaaS Subscription", r["subscription"], "billing_exception"), "Internal / Demo")

    def test_environment_not_allowed_leaves_it_approved(self):
        with patch.dict(frappe.local.conf, {"stemic_provision_environment": None}):
            r = self.onboard(start="Free trial")
        self.assertEqual(r["status"], "Approved")
        self.assertIsNone(r["job"])
        self.assertTrue(r["warnings"])

    def test_refused_step_names_itself(self):
        with self.assertRaises(frappe.ValidationError) as caught:
            self.onboard(start="Free trial", custom_domain="not a host")
        self.assertIn("Claim not a host", str(caught.exception))

    def test_taken_address_is_refused(self):
        self.onboard(start="Internal / Demo", when="draft")
        self.assertRaises(frappe.ValidationError, self.onboard, school_name="Another", start="Internal / Demo", when="draft")

    def test_operator_only(self):
        frappe.set_user("Guest")
        try:
            self.assertRaises(frappe.PermissionError, self.onboard, start="Free trial")
        finally:
            frappe.set_user("Administrator")


class TestAutomation(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._enqueue = patch.object(provisioner, "enqueue")
        self._enqueue.start()
        self.slug = "aut-" + frappe.generate_hash(length=6).lower()
        self.r = wizard.onboard_school("Automation School", "head@automation.test", plan(), start="Free trial",
                                       slug=self.slug, trial_days=5, when="draft")
        self.sub = self.r["subscription"]

    def tearDown(self):
        self._enqueue.stop()
        self._conf.stop()
        remove_school(self.slug)

    def test_trial_is_invoiced_and_reminded_before_it_ends(self):
        with patch.object(communications, "queue") as queued:
            billing.trials()
        invoice = billing.open_invoice(self.sub)
        self.assertTrue(invoice)
        # the first paid period starts the day after the trial
        self.assertEqual(str(frappe.db.get_value("SaaS Invoice", invoice, "period_start")), str(add_days(nowdate(), 5)))
        self.assertNotIn(("Trial Ending",), [c.args for c in queued.call_args_list])  # 4 days left: not yet
        frappe.db.set_value("SaaS Subscription", self.sub, "ends_on", add_days(nowdate(), 2))
        with patch.object(communications, "queue") as queued:
            billing.trials()
        queued.assert_any_call("Trial Ending", subscription=self.sub)

    def test_internal_schools_are_never_invoiced(self):
        frappe.db.set_value("SaaS Subscription", self.sub, "billing_exception", "Internal / Demo")
        billing.trials()
        self.assertFalse(billing.open_invoice(self.sub))

    def test_trial_reminder_renders(self):
        sub = frappe.get_doc("SaaS Subscription", self.sub)
        subject, html, sms = communications.render_trial_ending(sub)
        self.assertIn("trial", sms)
        self.assertIn("free trial", subject)
        self.assertIn("Automation School", html)

    def test_licence_waits_for_the_site(self):
        self.assertEqual(licensing.after_site_ready(self.slug), (None, "the school has no site yet"))

    def test_licence_switch_off(self):
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", f"{self.slug}.localhost")
        with patch.object(licensing, "_setting", return_value=False):
            license, why = licensing.after_site_ready(self.slug)
        self.assertIsNone(license)
        self.assertIn("switched off", why)

    def test_licence_issued_when_site_ready(self):
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", f"{self.slug}.localhost")
        with patch.object(licensing, "can_sign", return_value=True), \
                patch.object(licensing, "issue", return_value="LIC-TEST") as issue:
            self.assertEqual(licensing.after_site_ready(self.slug), ("LIC-TEST", None))
        issue.assert_called_once_with(self.sub)

    def test_cancelled_subscription_is_replaced_on_the_school(self):
        new = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.slug, "plan": plan(), "starts_on": nowdate()}).insert()
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "subscription"), self.sub)  # the first stays
        frappe.db.set_value("SaaS Subscription", self.sub, "status", "Cancelled")
        new.save()
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "subscription"), new.name)

    def test_overview_figures(self):
        data = dashboard.overview()
        self.assertEqual(len(data["months"]), 12)
        self.assertEqual([s["label"] for s in data["pipeline"]][-1], "Live")
        self.assertGreaterEqual(data["pipeline"][0]["count"], 1)  # this draft school
        self.assertIn(self.sub, [r.name for r in data["renewals"]])
        self.assertIn("mrr", data["money"])
