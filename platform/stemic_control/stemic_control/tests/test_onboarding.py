"""Who may get a school site: approval, commercial eligibility and the provisioning environment, denied by default.
bench --site <site> run-tests --module stemic_control.tests.test_onboarding"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_bench_path, nowdate

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, billing, onboarding, provisioner
from stemic_control.tests.helpers import approve, make_eligible, remove_school, subscription

LISTED = "frappe     16.0.0 version-16\nerpnext    16.0.0 version-16\nschool_erp 1.0.0   main\n"
CONF = {"stemic_platform_domain": "stemic.test", "stemic_local_provisioner": 1, "stemic_db_root_password": "root-secret-123",
        "stemic_site_domain": "localhost", "stemic_provision_environment": "development",
        "stemic_provision_allowed_benches": [get_bench_path()]}


class TestOnboarding(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._enqueue = patch.object(provisioner, "enqueue")
        self._enqueue.start()
        self.slug = "onb-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Onboarding School", self.slug, "head@onboarding.test")

    def tearDown(self):
        self._enqueue.stop()
        self._conf.stop()
        frappe.set_user("Administrator")
        remove_school(self.slug)

    def queue(self):
        return api.queue_provisioning(self.slug, "onb-" + frappe.generate_hash(length=12))

    def build(self, job):
        """Run the provisioner with the CLI mocked; returns its result and the commands it would have run."""
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            return LISTED if "list-apps" in args else ""
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            return provisioner.run(job), calls

    def operator(self, role):
        user = f"{role.split()[-1].lower()}-{frappe.generate_hash(length=6)}@onboarding.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": role, "send_welcome_email": 0,
                        "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return user

    # ------------------------------------------------------------------ approval
    def test_a_new_school_cannot_be_queued_until_approved(self):
        sub = subscription(self.slug)
        onboarding.grant_billing_exception(sub, onboarding.INTERNAL, "Internal test school")
        self.assertRaises(frappe.ValidationError, self.queue)  # Draft
        onboarding.submit_for_approval(self.slug)
        self.assertRaises(frappe.ValidationError, self.queue)  # Pending Approval
        onboarding.approve_tenant(self.slug, "Documents checked")
        tenant = frappe.get_doc("SaaS Tenant", self.slug)
        self.assertEqual((tenant.status, tenant.approved_by), ("Approved", "Administrator"))
        self.assertTrue(self.queue())

    def test_rejected_school_is_never_provisioned(self):
        make_eligible(self.slug)
        self.assertRaises(frappe.ValidationError, onboarding.reject_tenant, self.slug, "no")  # a reason is required
        onboarding.reject_tenant(self.slug, "Not a registered school")
        tenant = frappe.get_doc("SaaS Tenant", self.slug)
        self.assertEqual((tenant.status, tenant.approved_by, tenant.approval_note), ("Rejected", None, "Not a registered school"))
        self.assertRaises(frappe.ValidationError, self.queue)
        self.assertRaises(frappe.ValidationError, onboarding.submit_for_approval, self.slug)
        # back to Draft is the only way on, and then it needs approving again
        tenant.status = "Draft"
        tenant.save()
        self.assertRaises(frappe.ValidationError, self.queue)

    def test_a_school_with_a_queued_job_cannot_be_rejected(self):
        make_eligible(self.slug)
        self.queue()
        self.assertRaises(frappe.ValidationError, onboarding.reject_tenant, self.slug, "Changed our minds")

    def test_only_platform_admins_approve_or_grant_exceptions(self):
        onboarding.submit_for_approval(self.slug)
        sub = subscription(self.slug, status="Trial")
        for user in (self.operator("Stemic Agent"), "Guest"):
            frappe.set_user(user)
            self.assertRaises(frappe.PermissionError, onboarding.approve_tenant, self.slug, "Looks fine")
            self.assertRaises(frappe.PermissionError, onboarding.grant_billing_exception, sub, onboarding.FREE_TRIAL, "Trial please")
        frappe.set_user(self.operator("Stemic Platform Admin"))
        onboarding.approve_tenant(self.slug, "Looks fine")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Approved")

    def test_approvals_cannot_be_written_directly(self):
        tenant = frappe.get_doc("SaaS Tenant", self.slug)
        tenant.approved_by, tenant.approved_on = "Administrator", frappe.utils.now_datetime()
        self.assertRaises(frappe.PermissionError, tenant.save)
        sub = frappe.get_doc("SaaS Subscription", subscription(self.slug))
        sub.billing_exception, sub.exception_approved_on = onboarding.INTERNAL, frappe.utils.now_datetime()
        self.assertRaises(frappe.PermissionError, sub.save)
        self.assertRaises(frappe.PermissionError, frappe.get_doc({
            "doctype": "SaaS Tenant", "school_name": "Forged", "slug": self.slug + "x", "admin_email": "x@onboarding.test",
            "approved_by": "Administrator", "approved_on": frappe.utils.now_datetime()}).insert)

    # ------------------------------------------------------------------ commercial eligibility
    def test_unpaid_subscription_is_not_enough(self):
        approve(self.slug)
        self.assertRaises(frappe.ValidationError, self.queue)  # no subscription at all
        sub = subscription(self.slug)
        self.assertRaises(frappe.ValidationError, self.queue)  # a Trial nobody approved
        invoice = billing.create_invoice(sub, months=1)
        frappe.db.set_value("SaaS Subscription", sub, "status", "Active")  # e.g. activated by hand, nothing paid
        self.assertRaises(frappe.ValidationError, self.queue)
        billing.record_payment(invoice, frappe.db.get_value("SaaS Invoice", invoice, "total"), "M-Pesa", "QON" + frappe.generate_hash(length=7).upper())
        self.assertEqual(onboarding.commercial_basis(self.slug), "Paid subscription")
        self.assertTrue(self.queue())

    def test_approved_free_trial_may_be_provisioned_until_it_ends(self):
        approve(self.slug)
        sub = subscription(self.slug, status="Trial")
        self.assertRaises(frappe.ValidationError, onboarding.grant_billing_exception, sub, onboarding.FREE_TRIAL, "short")
        onboarding.grant_billing_exception(sub, onboarding.FREE_TRIAL, "Two-week pilot for the county")
        self.assertEqual(onboarding.commercial_basis(self.slug), onboarding.FREE_TRIAL)
        frappe.db.set_value("SaaS Subscription", sub, "ends_on", add_days(nowdate(), -1))
        self.assertIsNone(onboarding.commercial_basis(self.slug))  # an ended trial no longer counts
        self.assertRaises(frappe.ValidationError, self.queue)

    def test_a_free_trial_needs_a_trial_subscription(self):
        sub = subscription(self.slug)
        frappe.db.set_value("SaaS Subscription", sub, "status", "Past Due")
        self.assertRaises(frappe.ValidationError, onboarding.grant_billing_exception, sub, onboarding.FREE_TRIAL, "Pilot school")
        self.assertRaises(frappe.ValidationError, onboarding.grant_billing_exception, sub, "Free Forever", "Pilot school")

    def test_revoking_an_exception_stops_a_queued_build(self):
        sub = make_eligible(self.slug)
        job = self.queue()
        onboarding.revoke_billing_exception(sub)
        result, calls = self.build(job)
        self.assertEqual(result, "refused")
        self.assertEqual(calls, [])  # nothing was built
        row = frappe.db.get_value("SaaS Provisioning Job", job, ["status", "last_error"], as_dict=True)
        self.assertEqual(row.status, "Failed")
        self.assertIn("No paid subscription", row.last_error)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Approved")  # can be fixed and queued again

    # ------------------------------------------------------------------ environment
    def test_provisioner_refuses_an_unauthorised_environment(self):
        make_eligible(self.slug)
        for conf, expect in (({"stemic_provision_environment": None}, "stemic_provision_environment"),
                             ({"stemic_provision_environment": "laptop"}, "stemic_provision_environment"),
                             ({"stemic_provision_allowed_benches": ["/srv/other-bench"]}, "stemic_provision_allowed_benches"),
                             ({"stemic_provision_environment": "production"}, ".localhost")):
            job = self.queue()
            with patch.dict(frappe.local.conf, conf):
                result, calls = self.build(job)
            self.assertEqual((result, calls), ("refused", []), conf)
            self.assertIn(expect, frappe.db.get_value("SaaS Provisioning Job", job, "last_error"))
            self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Approved")

    def test_the_environment_comes_from_site_config_only(self):
        make_eligible(self.slug)
        job = self.queue()
        # the bench can be set on the Stemic Settings screen; it must still be one site_config allows
        with patch.dict(frappe.local.conf, {"stemic_bench_path": "/srv/other-bench"}):
            self.assertIn("stemic_provision_allowed_benches", onboarding.environment_problem())
        self.assertNotIn("environment", frappe.get_meta("SaaS Tenant").get_valid_columns())
        result, _calls = self.build(job)
        self.assertEqual(result, "Succeeded")
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", job, "environment"), "development")

    def test_an_eligible_school_is_built(self):
        make_eligible(self.slug)
        result, calls = self.build(self.queue())
        self.assertEqual(result, "Succeeded")
        self.assertEqual([c[0] for c in calls if c[0] == "new-site"], ["new-site"])
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Active")
