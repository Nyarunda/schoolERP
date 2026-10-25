"""Control-plane APIs against a database. Run on a disposable admin site:
bench --site <site> run-tests --module stemic_control.tests.test_integration"""

from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # older test base class
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api

DOMAIN = "stemic.test"


class TestControlPlane(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": DOMAIN})
        self._conf.start()
        self.slug = "school-" + frappe.generate_hash(length=6).lower()

    def tearDown(self):
        self._conf.stop()
        frappe.set_user("Administrator")

    def tenant(self, agent=None):
        return api.register_tenant("Greenfield Academy", self.slug, "head@greenfield.test", agent)

    def test_tenant_named_by_slug_and_duplicate_rejected(self):
        self.assertEqual(self.tenant(), self.slug)
        self.assertRaises(frappe.ValidationError, self.tenant)
        self.assertRaises(frappe.ValidationError, api.register_tenant, "X", "admin", "a@b.test")

    def test_subdomain_verified_custom_domain_needs_dns(self):
        t = self.tenant()
        sub = api.request_domain(t, f"{t}.{DOMAIN}")
        self.assertEqual((sub["domain"], sub["status"]), (f"{t}.{DOMAIN}", "Verified"))
        self.assertRaises(frappe.PermissionError, api.request_domain, t, f"other.{DOMAIN}")
        self.assertRaises(frappe.ValidationError, api.request_domain, t, f"admin.{DOMAIN}")
        self.assertRaises(frappe.ValidationError, api.request_domain, t, "not a host")

        custom = api.request_domain(t, f"portal.{t}.ac.test")
        self.assertEqual(custom["status"], "Pending Verification")
        self.assertEqual(custom["verification_record"], f"_stemic-verification.portal.{t}.ac.test")
        with patch.object(api, "_txt_records", return_value=["something-else"]):
            self.assertRaises(frappe.ValidationError, api.verify_domain, custom["domain"])
        with patch.object(api, "_txt_records", return_value=[custom["verification_value"]]):
            self.assertEqual(api.verify_domain(custom["domain"])["status"], "Verified")
        self.assertRaises(frappe.ValidationError, api.request_domain, t, f"portal.{t}.ac.test")

    def test_provisioning_is_idempotent_and_moves_the_tenant(self):
        t = self.tenant()
        key = "create-" + frappe.generate_hash(length=10)
        job = api.queue_provisioning(t, key)
        self.assertEqual(api.queue_provisioning(t, key), job)
        self.assertEqual(frappe.db.count("SaaS Provisioning Job", {"idempotency_key": key}), 1)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", t, "status"), "Pending")
        self.assertTrue(job.startswith("JOB-"))

        self.assertRaises(frappe.ValidationError, api.record_job_result, job, "Succeeded")  # must run first
        api.record_job_result(job, "Running")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", t, "status"), "Provisioning")
        api.record_job_result(job, "Succeeded")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", t, "status"), "Active")
        self.assertRaises(frappe.ValidationError, api.queue_provisioning, t, "another-key-123")

        self.assertEqual(api.set_tenant_status(t, "Suspended")["status"], "Suspended")
        self.assertEqual(api.set_tenant_status(t, "Active")["status"], "Active")

    def test_same_key_in_a_race_returns_the_winner(self):
        t = self.tenant()
        key = "race-" + frappe.generate_hash(length=10)
        job = api.queue_provisioning(t, key)
        real = frappe.db.get_value
        calls = {"n": 0}

        def first_lookup_misses(doctype, filters=None, *args, **kwargs):
            if doctype == "SaaS Provisioning Job" and calls["n"] == 0:
                calls["n"] += 1
                return None  # as if the other request had not committed yet
            return real(doctype, filters, *args, **kwargs)

        with patch.object(frappe.db, "get_value", side_effect=first_lookup_misses), patch.object(frappe.db, "rollback"):
            self.assertEqual(api.queue_provisioning(t, key), job)

    def test_tenant_status_rules(self):
        t = frappe.get_doc("SaaS Tenant", self.tenant())
        t.status = "Active"  # a Draft school cannot jump to Active
        self.assertRaises(frappe.ValidationError, t.save)

    def test_agents_see_only_their_schools(self):
        user = "agent-" + frappe.generate_hash(length=6) + "@stemic.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Agent", "send_welcome_email": 0,
            "roles": [{"role": "Stemic Agent"}]}).insert(ignore_permissions=True)
        mine = frappe.get_doc({"doctype": "SaaS Agent", "agent_name": "Agent", "user": user, "status": "Active"}).insert().name
        own = self.tenant(agent=mine)
        self.slug = "other-" + frappe.generate_hash(length=6).lower()
        other = self.tenant()

        frappe.set_user(user)
        visible = set(frappe.get_list("SaaS Tenant", pluck="name"))
        self.assertIn(own, visible)
        self.assertNotIn(other, visible)
        self.assertTrue(frappe.has_permission("SaaS Tenant", "read", own))
        self.assertFalse(frappe.has_permission("SaaS Tenant", "read", other))
        self.assertFalse(frappe.has_permission("SaaS Tenant", "write", own))
        self.assertRaises(frappe.PermissionError, api.overview)

    def test_guest_cannot_call_admin_apis(self):
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, api.overview)
        self.assertRaises(frappe.PermissionError, api.register_tenant, "X", "guest-school", "a@b.test")
