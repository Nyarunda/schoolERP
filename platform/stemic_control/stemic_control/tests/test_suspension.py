"""Suspend and Resume switch the school's own site, and the status only changes when the site does.
The Frappe CLI is faked (no site is touched).
bench --site <site> run-tests --module stemic_control.tests.test_suspension"""

from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, provisioner, site_runtime


class TestSuspension(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
        self._conf.start()
        slug = "sus-" + frappe.generate_hash(length=6).lower()
        self.tenant = api.register_tenant("Suspend Academy", slug, "head@suspend-academy.co.ke")
        self.site = f"{slug}.localhost"
        frappe.db.set_value("SaaS Tenant", self.tenant, {"status": "Active", "canonical_site": self.site})
        self.site_conf, self.calls = {}, []
        self._patches = [patch.object(provisioner, "_site_dir_exists", return_value=True),
                         patch.object(provisioner, "_frappe_cli", side_effect=self.cli),
                         patch.object(site_runtime, "_config", side_effect=lambda site: dict(self.site_conf))]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._conf.stop()
        frappe.db.rollback()

    def cli(self, *args, **kwargs):
        """A fake `frappe --site <site> set-config [-p] <key> <value>` that updates the fake site config."""
        self.calls.append(args)
        if "set-config" in args:
            key, value = args[-2], args[-1]
            import ast

            self.site_conf[key] = ast.literal_eval(value) if "-p" in args else value
        return ""

    def keys(self):
        return [c[-2] for c in self.calls if "set-config" in c]

    def test_suspend_blocks_the_site_and_pauses_its_jobs(self):
        api.set_tenant_status(self.tenant, "Suspended")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.tenant, "status"), "Suspended")
        self.assertEqual((self.site_conf["stemic_suspended"], self.site_conf["pause_scheduler"]), (1, 1))
        self.assertIn("Suspend Academy", self.site_conf["stemic_suspended_message"])
        self.assertEqual(self.keys()[-1], "stemic_suspended")  # the block starts last, once the message is in place
        self.assertTrue(all(c[:2] == ("--site", self.site) for c in self.calls))

    def test_the_page_gets_the_reason_and_what_is_owed(self):
        from stemic_control import billing

        plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Sus " + frappe.generate_hash(length=5), "enabled": 1,
                               "monthly_price": 5000, "modules": "[]"}).insert().name
        sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": plan,
                              "starts_on": frappe.utils.nowdate()}).insert().name
        inv = billing.create_invoice(sub, months=2)
        api.set_tenant_status(self.tenant, "Suspended", reason="Unpaid invoice")
        info = self.site_conf["stemic_suspension"]
        self.assertEqual((info["school"], info["reason"], info["invoice"]), ("Suspend Academy", "Unpaid invoice", inv))
        self.assertEqual(info["amount_due"], "KES 10,000.00")
        self.assertTrue(info["email"])

    def test_resume_unblocks_first_then_restarts_jobs(self):
        api.set_tenant_status(self.tenant, "Suspended")
        self.calls.clear()
        api.set_tenant_status(self.tenant, "Active")
        self.assertEqual(self.keys(), ["stemic_suspended", "pause_scheduler"])
        self.assertEqual((self.site_conf["stemic_suspended"], self.site_conf["pause_scheduler"]), (0, 0))
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.tenant, "status"), "Active")

    def test_if_the_site_cannot_be_switched_the_status_does_not_change(self):
        def broken(*args, **kwargs):
            self.calls.append(args)
            if "stemic_suspended" in args and args[-1] == "1":
                raise provisioner.ProvisioningError("set-config failed")
            return self.cli(*args)

        with patch.object(provisioner, "_frappe_cli", side_effect=broken):
            self.assertRaises(provisioner.ProvisioningError, api.set_tenant_status, self.tenant, "Suspended")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.tenant, "status"), "Active")
        self.assertFalse(self.site_conf.get("stemic_suspended"))
        self.assertEqual(self.site_conf.get("pause_scheduler"), 0)  # put back as it was

    def test_a_site_on_another_server_is_refused(self):
        with patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertRaises(frappe.ValidationError, api.set_tenant_status, self.tenant, "Suspended")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.tenant, "status"), "Active")

    def test_a_school_without_a_site_only_changes_status(self):
        frappe.db.set_value("SaaS Tenant", self.tenant, "canonical_site", None)
        api.set_tenant_status(self.tenant, "Suspended")
        self.assertEqual(self.calls, [])
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.tenant, "status"), "Suspended")

    def test_the_status_cannot_be_typed_in_by_hand(self):
        doc = frappe.get_doc("SaaS Tenant", self.tenant)
        doc.status = "Suspended"
        self.assertRaises(frappe.ValidationError, doc.save)
        self.assertEqual(self.calls, [])
