"""Control-plane APIs against a database. Run on a disposable admin site:
bench --site <site> run-tests --module stemic_control.tests.test_integration"""

from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # older test base class
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api
from stemic_control.tests.helpers import make_eligible

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

    def eligible(self):
        t = self.tenant()
        make_eligible(t)
        return t

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
        t = self.eligible()
        key = "create-" + frappe.generate_hash(length=10)
        job = api.queue_provisioning(t, key)
        self.assertEqual(api.queue_provisioning(t, key), job)
        self.assertEqual(frappe.db.count("SaaS Provisioning Job", {"idempotency_key": key}), 1)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", t, "status"), "Pending")
        self.assertTrue(job.startswith("JOB-"))

        self.assertRaises(frappe.ValidationError, api.record_job_result, job, "Succeeded")  # must run first
        api.record_job_result(job, "Running")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", t, "status"), "Provisioning")
        self.assertRaises(frappe.ValidationError, api.record_job_result, job, "Succeeded")
        api.record_job_result(job, "Failed", "Provisioner is not installed")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", t, "status"), "Failed")
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", job, "status"), "Failed")

    def test_competing_job_keys_rejected(self):
        t = self.eligible()
        api.queue_provisioning(t, "primary-" + frappe.generate_hash(length=12))
        self.assertRaises(frappe.ValidationError, api.queue_provisioning, t, "secondary-" + frappe.generate_hash(length=12))

    def test_cannot_forge_custom_domain_verification(self):
        t = self.tenant()
        data = api.request_domain(t, f"portal.{t}.ac.test")
        doc = frappe.get_doc("SaaS Domain", data["domain"])
        doc.status = "Verified"
        self.assertRaises(frappe.PermissionError, doc.save)
        doc.reload()
        doc.tenant = "someone-else"
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_job_status_cannot_be_edited_directly(self):
        t = self.eligible()
        name = api.queue_provisioning(t, "secure-" + frappe.generate_hash(length=12))
        doc = frappe.get_doc("SaaS Provisioning Job", name)
        doc.status = "Succeeded"
        self.assertRaises(frappe.PermissionError, doc.save)

    def test_same_key_in_a_race_returns_the_winner(self):
        t = self.eligible()
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

    def test_platform_admins_can_open_records(self):
        """Only Administrator skips permission hooks; a real operator must still open any school or subscription."""
        user = "operator-" + frappe.generate_hash(length=6) + "@stemic.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Operator", "send_welcome_email": 0,
            "roles": [{"role": "Stemic Platform Admin"}]}).insert(ignore_permissions=True)
        tenant = self.tenant()
        plan = frappe.db.get_value("SaaS Plan", {}) or frappe.get_doc({"doctype": "SaaS Plan",
            "plan_name": "Plan " + frappe.generate_hash(length=4), "enabled": 1}).insert().name
        sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": tenant, "plan": plan,
            "starts_on": frappe.utils.nowdate()}).insert().name

        frappe.set_user(user)
        for doctype, name in (("SaaS Tenant", tenant), ("SaaS Subscription", sub)):
            self.assertTrue(frappe.has_permission(doctype, "read", name), doctype)
            self.assertTrue(frappe.has_permission(doctype, "write", name), doctype)
        self.assertEqual(frappe.get_doc("SaaS Tenant", tenant).slug, tenant)
        self.assertIn("schools", api.dashboard_metrics())

    def test_guest_cannot_call_admin_apis(self):
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, api.overview)
        self.assertRaises(frappe.PermissionError, api.register_tenant, "X", "guest-school", "a@b.test")

    def test_attention_feed_names_schools_and_hides_retried_failures(self):
        failed = self.tenant()
        frappe.db.set_value("SaaS Tenant", failed, "status", "Failed")
        job = frappe.get_doc({"doctype": "SaaS Provisioning Job", "tenant": failed, "action": "Create Site",
                              "idempotency_key": "att-" + frappe.generate_hash(length=10), "status": "Queued"}).insert()
        frappe.db.set_value("SaaS Provisioning Job", job.name, {"status": "Failed", "last_error": "\nDatabase refused\nmore"})
        self.slug = "retried-" + frappe.generate_hash(length=6).lower()
        retried = self.tenant()  # its old job failed, but the school was queued again
        frappe.db.set_value("SaaS Tenant", retried, "status", "Pending")

        groups = {g["key"]: g for g in api.operations_queue(per_group=10)["groups"]}
        self.assertEqual(set(groups), {"background", "failed_sites", "overdue", "unpaid_invoices", "dns", "domain_live", "approval", "creating"})  # every group, even when empty
        failed_item = next(i for i in groups["failed_sites"]["items"] if i["name"] == failed)
        self.assertEqual((failed_item["school"], failed_item["detail"]), ("Greenfield Academy", "Database refused"))
        self.assertNotIn(retried, [i["name"] for i in groups["failed_sites"]["items"]])
        self.assertIn(retried, [i["name"] for i in groups["creating"]["items"]])
        self.assertEqual(groups["failed_sites"]["count"], frappe.db.count("SaaS Tenant", {"status": "Failed"}))
        self.assertLessEqual(len(api.operations_queue(per_group=1)["groups"][0]["items"]), 1)

    def test_attention_feed_is_for_platform_admins_only(self):
        user = "agent-" + frappe.generate_hash(length=6) + "@stemic.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Agent", "send_welcome_email": 0,
            "roles": [{"role": "Stemic Agent"}]}).insert(ignore_permissions=True)
        frappe.set_user(user)
        self.assertRaises(frappe.PermissionError, api.operations_queue)
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, api.operations_queue)
