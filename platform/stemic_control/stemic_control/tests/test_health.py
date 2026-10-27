"""Is the background machinery running (stemic_control.health), as the watchdog and the Control Center report it.
bench --site <site> run-tests --module stemic_control.tests.test_health"""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, health, provisioner
from stemic_control.tests.helpers import remove_school


class TestHealth(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.sql("UPDATE `tabScheduled Job Type` SET last_execution = %s WHERE stopped = 0", (now_datetime(),))
        self.slug = None
        # Frappe reports the scheduler as off while tests run; these tests decide it themselves
        self._scheduler = patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=False)
        self._scheduler.start()

    def tearDown(self):
        self._scheduler.stop()
        if self.slug:
            remove_school(self.slug)

    def keys(self):
        return {p["key"] for p in health.check()}

    def test_a_healthy_bench_reports_nothing(self):
        with patch.object(health, "_workers", return_value=(1, 0)), patch.object(provisioner, "enabled", return_value=False):
            self.assertEqual(self.keys(), set())

    def test_no_worker_a_backlog_and_an_unreachable_queue(self):
        with patch.object(health, "_workers", return_value=(0, 0)):
            self.assertIn("workers", self.keys())
        with patch.object(health, "_workers", return_value=(2, health.QUEUE_WAIT + 5)):
            self.assertIn("backlog", self.keys())
        with patch.object(health, "_workers", side_effect=ConnectionError("Connection refused")):
            problems = {p["key"]: p for p in health.check()}
            self.assertIn("redis", problems)
            self.assertIn("Connection refused", problems["redis"]["message"])

    def test_a_scheduler_switched_off(self):
        with patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=True), patch.object(health, "_workers", return_value=(1, 0)):
            self.assertIn("scheduler_off", self.keys())

    def test_a_silent_scheduler(self):
        old = add_to_date(now_datetime(), minutes=-(health.SCHEDULER_SILENT + 10))
        frappe.db.sql("UPDATE `tabScheduled Job Type` SET last_execution = %s WHERE stopped = 0", (old,))
        with patch.object(health, "_workers", return_value=(1, 0)):
            self.assertIn("scheduler_stopped", self.keys())

    def test_site_jobs_left_waiting_but_not_demo_schools(self):
        self.slug = "hlth-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Health School", self.slug, "head@health.test")
        job = frappe.get_doc({"doctype": "SaaS Provisioning Job", "tenant": self.slug, "action": "Create Site",
                              "idempotency_key": "hlth-" + frappe.generate_hash(length=10), "status": "Queued"}).insert().name
        frappe.db.sql("UPDATE `tabSaaS Provisioning Job` SET creation = %s WHERE name = %s",
                      (add_to_date(now_datetime(), minutes=-(health.PROVISION_WAIT + 5)), job))
        with patch.object(health, "_workers", return_value=(1, 0)), patch.object(provisioner, "enabled", return_value=True):
            self.assertIn("provisioning", self.keys())
            frappe.db.set_value("SaaS Tenant", self.slug, "notes", provisioner.DEMO_NOTE)  # demo schools are never built
            self.assertNotIn("provisioning", self.keys())

    def test_the_control_center_shows_it_first(self):
        with patch.object(health, "_workers", return_value=(0, 0)):
            groups = api.operations_queue(per_group=5)["groups"]
        self.assertEqual(groups[0]["key"], "background")
        self.assertGreaterEqual(groups[0]["count"], 1)
        self.assertIn("No background worker is running", groups[0]["items"][0]["school"])
