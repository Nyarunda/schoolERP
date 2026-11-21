"""Control Center automation (specs/features/control-center-automation).
bench --site <site> run-tests --module stemic_control.tests.test_service"""

from collections import namedtuple
from unittest.mock import patch

import frappe

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # older Frappe
	from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, service, site_runtime

Usage = namedtuple("Usage", "total used free")
GB = 1024 ** 3


class TestService(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.tenants = []
		for i in range(2):
			slug = f"sv{i}-" + frappe.generate_hash(length=5).lower()
			api.register_tenant(f"Service School {i}", slug, f"head{i}@{slug}.test")
			frappe.db.set_value("SaaS Tenant", slug, {"canonical_site": f"{slug}.localhost", "status": "Active"})
			self.tenants.append(frappe._dict(name=slug, canonical_site=f"{slug}.localhost"))
		self._live = patch.object(service, "_live", return_value=self.tenants)
		self._live.start()
		frappe.cache.delete_value(service.CACHE)
		for k, v in {"watch_schools": 1, "update_after_code_change": 1, "disk_alert_percent": 10, "last_code_version": None}.items():
			frappe.db.set_single_value("Stemic Settings", k, v)
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

	def tearDown(self):
		self._live.stop()
		frappe.cache.delete_value(service.CACHE)
		frappe.set_user("Administrator")

	def test_update_all_batches(self):
		busy = frappe._dict(action="Backup", name="SITEOP-X")
		with patch.object(site_runtime, "_active_operation", side_effect=lambda site: busy if site == self.tenants[1].canonical_site else None), \
				patch.object(frappe, "enqueue") as enqueue:
			r = service.update_all_schools()
		self.assertEqual(r["queued"], 1)
		self.assertEqual([s["tenant"] for s in r["skipped"]], [self.tenants[1].name])
		self.assertEqual(enqueue.call_count, 1)
		self.assertEqual(enqueue.call_args.kwargs["batch"], r["batch"])
		ops = frappe.get_all("SaaS Site Operation", filters={"batch": r["batch"]}, fields=["action", "status", "trigger"])
		self.assertEqual([(o.action, o.status, o.trigger) for o in ops], [("Migrate", "Queued", "Bulk")])

	def test_process_batch_in_order(self):
		with patch.object(frappe, "enqueue"):
			r = service.start_batch(self.tenants, "Clear Cache")
		ran = []
		with patch.object(site_runtime, "perform_operation", side_effect=lambda op: ran.append(op) or "Succeeded"):
			results = service.process_batch(r["batch"])
		ops = frappe.get_all("SaaS Site Operation", filters={"batch": r["batch"]}, pluck="name", order_by="creation asc")
		self.assertEqual(ran, ops)
		self.assertEqual(set(results.values()), {"Succeeded"})
		self.assertEqual(len(service.batch_status(r["batch"])), 2)

	def test_auto_update_once_per_commit(self):
		with patch.object(service, "code_version", return_value="aaa111"), patch.object(frappe, "enqueue"):
			self.assertIsNone(service.auto_update())  # first sight: just recorded
			self.assertIsNone(service.auto_update())  # same commit
		with patch.object(service, "code_version", return_value="bbb222"), patch.object(frappe, "enqueue"):
			r = service.auto_update()
			self.assertEqual(r["queued"], 2)
			self.assertIsNone(service.auto_update())
		ops = frappe.get_all("SaaS Site Operation", filters={"batch": r["batch"]}, pluck="trigger")
		self.assertEqual(set(ops), {"After update"})

	def test_bulk_action(self):
		with patch.object(frappe, "enqueue"):
			r = service.bulk_action(frappe.as_json([self.tenants[0].name, "not-a-school"]), "Backup")
		self.assertEqual(r["queued"], 1)
		self.assertEqual(r["not_here"], ["not-a-school"])
		self.assertRaises(frappe.ValidationError, service.bulk_action, frappe.as_json([self.tenants[0].name]), "Restore")

	def test_watch_alerts_on_change(self):
		answers = {self.tenants[0].canonical_site: [False, False, False, True], self.tenants[1].canonical_site: [True] * 4}
		with patch.object(site_runtime, "served_at", side_effect=lambda site, primary=None: ["x"] if answers[site].pop(0) else []), \
				patch("shutil.disk_usage", return_value=Usage(1000 * GB, 500 * GB, 500 * GB)), \
				patch("stemic_control.alerts.notify_admins") as alert:
			for _ in range(4):
				service.watch()
		titles = [c.args[0] for c in alert.call_args_list]
		self.assertEqual(len(titles), 2)
		self.assertIn("is not answering", titles[0])
		self.assertIn("is answering again", titles[1])
		with patch.object(site_runtime, "served_at", return_value=["x"]), \
				patch("shutil.disk_usage", return_value=Usage(1000 * GB, 980 * GB, 20 * GB)), \
				patch("stemic_control.alerts.notify_admins") as alert:
			service.watch()
			service.watch()  # once per problem
		self.assertEqual([c.args[0] for c in alert.call_args_list], ["The server is running out of disk space"])

	def test_service_health(self):
		with patch("stemic_control.health.check", return_value=[{"key": "workers", "message": "No worker", "fix": "start"}]), \
				patch("shutil.disk_usage", return_value=Usage(100 * GB, 50 * GB, 50 * GB)):
			h = service.service_health()
		self.assertEqual(h["machinery"][0]["key"], "workers")
		self.assertEqual(h["disk"]["free_gb"], 50.0)
		self.assertEqual({s["tenant"] for s in h["schools"]}, {t.name for t in self.tenants})

	def test_maintenance_notice(self):
		with patch.object(frappe, "sendmail") as mail:
			r = service.notify_maintenance(frappe.as_json([t.name for t in self.tenants]), "Saturday 10pm", "We will update.")
		self.assertEqual(set(r["sent"]), {t.name for t in self.tenants})
		self.assertEqual(mail.call_count, 2)
		self.assertRaises(frappe.ValidationError, service.notify_maintenance, frappe.as_json([self.tenants[0].name]), "", "x")

	def test_admin_only(self):
		email = "not.admin@service.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Not Admin", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		for call in (service.update_all_schools, service.service_health, lambda: service.batch_status("x"),
					 lambda: service.bulk_action("[]", "Backup"), lambda: service.notify_maintenance("[]", "a", "b")):
			self.assertRaises(frappe.PermissionError, call)
