"""Local provisioner against a database, with Frappe's CLI mocked (no real sites are created).
bench --site <site> run-tests --module stemic_control.tests.test_provisioner"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, provisioner

CONF = {"stemic_platform_domain": "stemic.test", "stemic_local_provisioner": 1, "stemic_db_root_password": "root-secret-123",
        "stemic_site_domain": "localhost"}
LISTED = "frappe     16.0.0 version-16\nerpnext    16.0.0 version-16\nschool_erp 1.0.0   main\n"


class TestProvisioner(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._enqueue = patch.object(provisioner, "enqueue")  # tests call run() directly
        self._enqueue.start()
        self.slug = "prov-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Provisioned School", self.slug, "head@prov.test")
        api.request_domain(self.slug, f"{self.slug}.stemic.test")
        self.job = api.queue_provisioning(self.slug, "prov-" + frappe.generate_hash(length=12))

    def tearDown(self):
        self._enqueue.stop()
        self._conf.stop()

    def cli(self, fail_new_site=False):
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            if args[0] == "new-site" and fail_new_site:
                raise provisioner.ProvisioningError("new-site failed: database error")
            return LISTED if "list-apps" in args else ""
        return calls, fake

    def test_does_nothing_when_switched_off(self):
        with patch.dict(frappe.local.conf, {"stemic_local_provisioner": 0}):
            self.assertEqual(provisioner.run(self.job), "disabled")
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", self.job, "status"), "Queued")

    def test_success_activates_school_and_stores_password(self):
        calls, fake = self.cli()
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertEqual(provisioner.run(self.job), "Succeeded")
        site = f"{self.slug}.localhost"
        new_site = next(c for c in calls if c[0] == "new-site")
        self.assertEqual(new_site[1], site)
        self.assertIn("school_erp", new_site)
        self.assertTrue(any("list-apps" in c for c in calls))  # readiness checked before success
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", self.job, "status"), "Succeeded")
        tenant = frappe.get_doc("SaaS Tenant", self.slug)
        self.assertEqual((tenant.status, tenant.canonical_site), ("Active", site))
        self.assertEqual(frappe.db.get_value("SaaS Domain", f"{self.slug}.stemic.test", "status"), "Active")
        access = api.site_access(self.slug)
        self.assertEqual(access["site"], site)
        self.assertTrue(access["password"] and access["password"] != "*" * len(access["password"]))
        self.assertEqual(provisioner.run(self.job), "Succeeded")  # a second run does nothing

    def test_failure_marks_job_and_school_failed(self):
        calls, fake = self.cli(fail_new_site=True)
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", side_effect=[False, True]):
            self.assertEqual(provisioner.run(self.job), "Failed")
        job = frappe.get_doc("SaaS Provisioning Job", self.job)
        self.assertEqual(job.status, "Failed")
        self.assertIn("database error", job.last_error)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Failed")
        self.assertTrue(any(c[0] == "drop-site" for c in calls))  # the half-made site is cleaned up

    def test_secrets_are_scrubbed_from_command_output(self):
        result = SimpleNamespace(stdout="Access denied using password root-secret-123", stderr="", returncode=1)
        with patch("subprocess.run", return_value=result):
            with self.assertRaises(provisioner.ProvisioningError) as caught:
                provisioner._frappe_cli("new-site", "x.localhost", secrets_=("root-secret-123",))
        self.assertNotIn("root-secret-123", str(caught.exception))
        self.assertIn("********", str(caught.exception))

    def test_demo_schools_are_never_provisioned(self):
        frappe.db.set_value("SaaS Tenant", self.slug, "notes", provisioner.DEMO_NOTE)
        with patch.object(provisioner, "_frappe_cli") as cli:
            self.assertTrue(provisioner.run(self.job).startswith("skipped"))
        cli.assert_not_called()

    def test_manual_success_still_blocked(self):
        api.record_job_result(self.job, "Running")
        self.assertRaises(frappe.ValidationError, api.record_job_result, self.job, "Succeeded")

    def test_operator_mark_failed_while_running_is_respected(self):
        def fake(*args, **kwargs):
            if args[0] == "new-site":  # an operator gives up on the job while the site is still being built
                api.record_job_result(self.job, "Failed", "Stopped by an operator")
            return LISTED if "list-apps" in args else ""
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertEqual(provisioner.run(self.job), "Closed by operator")
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", self.job, "status"), "Failed")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Failed")

    def test_manual_buttons(self):
        # Provision Now on a Pending school hands its queued job over
        self.assertEqual(api.provision_tenant_now(self.slug)["job"], self.job)
        provisioner.enqueue.assert_called_with(self.job)
        # Process Queue Now hands over real schools' queued jobs and skips demo ones
        provisioner.enqueue.reset_mock()
        handed = api.process_queue_now()["handed_to_worker"]
        self.assertGreaterEqual(handed, 1)
        self.assertIn(self.job, [c.args[0] for c in provisioner.enqueue.call_args_list])
        frappe.db.set_value("SaaS Tenant", self.slug, "notes", provisioner.DEMO_NOTE)
        provisioner.enqueue.reset_mock()
        api.process_queue_now()
        self.assertNotIn(self.job, [c.args[0] for c in provisioner.enqueue.call_args_list])
        # nothing queued: say so instead of failing silently
        frappe.db.set_value("SaaS Provisioning Job", self.job, "status", "Failed")
        self.assertRaises(frappe.ValidationError, api.provision_tenant_now, self.slug)
