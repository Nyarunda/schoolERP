"""Platform admins are told (bell notification, emailed by Frappe) when something needs them.
bench --site <site> run-tests --module stemic_control.tests.test_alerts"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_bench_path, nowdate

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import alerts, api, billing, onboarding, provisioner, site_runtime
from stemic_control.tests.helpers import make_eligible, remove_school

CONF = {"stemic_platform_domain": "stemic.test", "stemic_local_provisioner": 1, "stemic_db_root_password": "root-secret-123",
        "stemic_site_domain": "localhost", "stemic_provision_environment": "development",
        "stemic_provision_allowed_benches": [get_bench_path()]}


class TestAlerts(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._enqueue = patch.object(provisioner, "enqueue")
        self._enqueue.start()
        self.admin = f"ops-{frappe.generate_hash(length=6)}@alerts.test"
        frappe.get_doc({"doctype": "User", "email": self.admin, "first_name": "Ops", "send_welcome_email": 0,
                        "roles": [{"role": "Stemic Platform Admin"}]}).insert(ignore_permissions=True)
        self.slug = "alrt-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Alert School", self.slug, "head@alerts.test")

    def tearDown(self):
        self._enqueue.stop()
        self._conf.stop()
        remove_school(self.slug)  # rolls back, then removes what the provisioner's commits kept
        # the provisioner commits, so the test admin and their notifications would outlive the test
        frappe.db.delete("Notification Log", {"for_user": self.admin})
        frappe.db.delete("Has Role", {"parent": self.admin})
        frappe.db.delete("User", {"name": self.admin})
        frappe.db.commit()

    def alerts_for(self, doctype, name):
        return frappe.get_all("Notification Log", filters={"for_user": self.admin, "document_type": doctype, "document_name": name},
                              fields=["title", "type"])

    def test_a_refused_build_alerts_the_admins(self):
        sub = make_eligible(self.slug)
        job = api.queue_provisioning(self.slug, "alrt-" + frappe.generate_hash(length=12))
        onboarding.revoke_billing_exception(sub)
        with patch.object(provisioner, "_frappe_cli") as cli:
            self.assertEqual(provisioner.run(job), "refused")
        cli.assert_not_called()
        sent = self.alerts_for("SaaS Provisioning Job", job)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].title, "The site for Alert School was refused")

    def test_a_failed_build_alerts_the_admins(self):
        make_eligible(self.slug)
        job = api.queue_provisioning(self.slug, "alrt-" + frappe.generate_hash(length=12))

        def fail(*args, **kwargs):
            if args[0] == "new-site":
                raise provisioner.ProvisioningError("new-site failed: database error")
            return ""
        with patch.object(provisioner, "_frappe_cli", side_effect=fail), patch.object(provisioner, "_site_dir_exists", return_value=False), \
                patch.object(provisioner, "_database_exists", return_value=False):
            self.assertEqual(provisioner.run(job), "Failed")
        self.assertEqual([a.title for a in self.alerts_for("SaaS Provisioning Job", job)], ["Creating the site for Alert School failed"])

    def test_a_failed_site_operation_alerts_the_admins(self):
        site = f"{self.slug}.localhost"
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", site)
        real = site_runtime._site_dir(frappe.local.site)
        with patch.object(site_runtime, "_site_dir", side_effect=lambda s: real if s == site else f"/nonexistent/{s}"):
            with patch.object(frappe, "enqueue"):  # only the operation's own job; the alert is enqueued for real
                op = site_runtime.run_operation(self.slug, "Backup")["operation"]
            with patch.object(site_runtime, "_set", side_effect=lambda o, v: frappe.db.set_value("SaaS Site Operation", o, v)), \
                    patch.object(provisioner, "_frappe_cli", side_effect=provisioner.ProvisioningError("backup failed: disk full")):
                self.assertEqual(site_runtime.perform_operation(op), "Failed")
        self.assertEqual([a.title for a in self.alerts_for("SaaS Site Operation", op)], [f"Backup failed on {site}"])

    def test_invoices_that_disagree_alert_the_admins(self):
        plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Alert " + frappe.generate_hash(length=5), "enabled": 1,
                               "monthly_price": 1000, "modules": "[]"}).insert().name
        sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.slug, "plan": plan, "starts_on": nowdate(),
                              "ends_on": add_days(nowdate(), 30)}).insert().name
        inv = billing.create_invoice(sub, months=1)
        frappe.db.set_value("SaaS Invoice", inv, "paid_amount", 500)  # disagrees with its (no) payments
        with patch.object(frappe.db, "commit"):
            billing.check_ledger()
        log = frappe.get_all("Error Log", filters={"method": ("like", "Billing ledger:%")}, pluck="name", order_by="creation desc", limit=1)[0]
        sent = self.alerts_for("Error Log", log)
        self.assertEqual(len(sent), 1)
        self.assertIn("disagree with their payments", sent[0].title)

    def test_the_same_alert_is_not_repeated(self):
        for _ in range(2):
            alerts.notify_admins("Test alert", "once only", "SaaS Tenant", self.slug)
        self.assertEqual(len(self.alerts_for("SaaS Tenant", self.slug)), 1)
        self.assertIn(self.admin, alerts.platform_admins())
