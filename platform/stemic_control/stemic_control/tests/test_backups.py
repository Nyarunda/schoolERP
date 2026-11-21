"""School backups and restore from the Control Center (specs/features/control-center-backups).
bench --site <site> run-tests --module stemic_control.tests.test_backups"""

import datetime as dt
import os
from unittest.mock import patch

import frappe
try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # older Frappe
	from frappe.tests.utils import FrappeTestCase as TestCase
from frappe.utils import get_bench_path, now_datetime

from stemic_control import api, backups, provisioner, site_runtime


class FakeStore:
	def __init__(self, fail=None):
		self.bucket, self.prefix, self.fail = "school-backups", "stemic", fail
		self.objects, self.deleted = {}, []

	def key(self, site, path):
		from stemic_control.backup_rules import object_key

		return object_key(self.prefix, site, path)

	def upload(self, path, key):
		if self.fail:
			raise RuntimeError(self.fail)
		self.objects[key] = path

	def download(self, key, path):
		with open(path, "w") as f:
			f.write("downloaded")

	def delete(self, key):
		self.deleted.append(key)
		self.objects.pop(key, None)

	def link(self, key, seconds=900):
		return f"https://storage.example/{key}?sig=1"


class TestBackups(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._conf = patch.dict(frappe.local.conf, {"stemic_provision_environment": "development",
													"stemic_provision_allowed_benches": [get_bench_path()]})
		self._conf.start()
		self.slug = "bk-" + frappe.generate_hash(length=6).lower()
		self.site = f"{self.slug}.localhost"
		api.register_tenant("Backup School", self.slug, "head@backup.test")
		frappe.db.set_value("SaaS Tenant", self.slug, {"canonical_site": self.site, "status": "Active"})
		real = site_runtime._site_dir(frappe.local.site)
		self._dir = patch.object(site_runtime, "_site_dir", side_effect=lambda site: real if site == self.site else f"/nonexistent/{site}")
		self._dir.start()
		self.folder = os.path.join(real, "private", "backups")
		os.makedirs(self.folder, exist_ok=True)
		self.made = []
		self.set_settings(backup_destination="This server only", nightly_backups=1, backup_hour=0, last_nightly_run=None,
						  keep_daily=7, keep_weekly=4, keep_monthly=6, keep_offsite_days=90, backup_with_files=1)

	def tearDown(self):
		for path in self.made:
			if os.path.isfile(path):
				os.unlink(path)
		self._dir.stop()
		self._conf.stop()
		frappe.set_user("Administrator")

	# ------------------------------------------------------------------ helpers
	def set_settings(self, **values):
		for k, v in values.items():
			frappe.db.set_single_value("Stemic Settings", k, v)
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

	def fake_files(self, when):
		stamp = when.strftime("%Y%m%d_%H%M%S")
		base = os.path.join(self.folder, f"{stamp}-{self.slug.replace('-', '_')}")
		paths = {"Database": base + "-database.sql.gz", "Public": base + "-files.tar", "Private": base + "-private-files.tar",
				 "Config": base + "-site_config_backup.json"}
		for p in paths.values():
			with open(p, "w") as f:
				f.write("x" * 1024)
			self.made.append(p)
		return "\n".join(f"{k:<8}: {v} 1.0KiB" for k, v in paths.items())

	def take_backup(self, when=None, trigger="Manual"):
		output = self.fake_files(when or now_datetime())
		op = site_runtime.queue_operation(self.slug, self.site, "Backup", trigger=trigger, enqueue=False)
		with patch.object(site_runtime, "_set", side_effect=lambda o, v: frappe.db.set_value("SaaS Site Operation", o, v)), \
				patch.object(provisioner, "_frappe_cli", return_value=output):
			self.assertEqual(site_runtime.perform_operation(op), "Succeeded")
		return frappe.db.get_value("SaaS Site Operation", op, "backup")

	# ------------------------------------------------------------------ tests
	def test_backup_is_recorded(self):
		name = self.take_backup()
		b = frappe.get_doc("SaaS Backup", name)
		self.assertEqual((b.tenant, b.site, b.kind, b.on_server, b.offsite_status, b.status),
						 (self.slug, self.site, "Manual", 1, "Not set up", "Available"))
		self.assertTrue(b.database_file.endswith("-database.sql.gz") and b.private_file.endswith("-private-files.tar"))

	def test_offsite_upload(self):
		self.set_settings(backup_destination="This server + S3-compatible storage", s3_bucket="school-backups")
		store = FakeStore()
		with patch.object(backups, "storage", return_value=store):
			name = self.take_backup()
		b = frappe.get_doc("SaaS Backup", name)
		self.assertEqual(b.offsite_status, "Uploaded")
		self.assertEqual(len(store.objects), 4)
		self.assertTrue(all(k.startswith(f"stemic/{self.site}/") for k in store.objects))
		with patch.object(backups, "storage", return_value=FakeStore(fail="AccessDenied")), \
				patch("stemic_control.alerts.notify_admins") as alert:
			failed = self.take_backup(now_datetime() + dt.timedelta(seconds=2))
		self.assertEqual(frappe.db.get_value("SaaS Backup", failed, "offsite_status"), "Failed")
		self.assertIn("Off-server copy failed", alert.call_args.args[0])

	def test_test_destination(self):
		self.assertTrue(backups.test_destination()["ok"])  # server only: nothing to test
		self.set_settings(backup_destination="This server + S3-compatible storage", s3_bucket="school-backups")
		with patch.object(backups, "storage", return_value=FakeStore()):
			self.assertTrue(backups.test_destination()["ok"])
		with patch.object(backups, "storage", return_value=FakeStore(fail="InvalidAccessKeyId")):
			r = backups.test_destination()
		self.assertFalse(r["ok"])
		self.assertIn("InvalidAccessKeyId", r["message"])

	def test_nightly_queue(self):
		tenant = frappe._dict(name=self.slug, canonical_site=self.site)
		with patch.object(backups, "_live_tenants", return_value=[tenant]), patch.object(frappe, "enqueue") as enqueue, \
				patch.object(backups, "watchdog"), patch.object(backups, "prune"):
			backups.hourly()
			backups.hourly()  # same day: not again
		ops = frappe.get_all("SaaS Site Operation", filters={"site": self.site, "action": "Backup", "trigger": "Scheduled"})
		self.assertEqual(len(ops), 1)
		self.assertEqual(enqueue.call_count, 1)

	def test_prune(self):
		self.set_settings(keep_daily=2, keep_weekly=0, keep_monthly=0)
		start = now_datetime().replace(microsecond=0)
		names = [self.take_backup(start - dt.timedelta(days=i)) for i in range(5)]
		backups.toggle_pin(names[4])
		backups.prune()
		state = {n: frappe.db.get_value("SaaS Backup", n, ["status", "on_server"]) for n in names}
		self.assertEqual(state[names[0]], ("Available", 1))
		self.assertEqual(state[names[1]], ("Available", 1))
		self.assertEqual(state[names[2]], ("Removed", 0))
		self.assertEqual(state[names[4]], ("Available", 1))  # pinned
		self.assertFalse(os.path.exists(frappe.db.get_value("SaaS Backup", names[2], "database_file")))
		# off-server: copies older than N days go, pinned stay
		self.set_settings(backup_destination="This server + S3-compatible storage", s3_bucket="b", keep_offsite_days=2)
		for n in (names[3], names[4]):  # copied off-server before the server copy went
			frappe.db.set_value("SaaS Backup", n, {"offsite_status": "Uploaded", "status": "Available"})
		store = FakeStore()
		with patch.object(backups, "storage", return_value=store):
			backups.prune()
		self.assertEqual(frappe.db.get_value("SaaS Backup", names[3], "offsite_status"), "Removed")
		self.assertEqual(frappe.db.get_value("SaaS Backup", names[4], "offsite_status"), "Uploaded")
		self.assertTrue(store.deleted)

	def test_watchdog(self):
		tenant = frappe._dict(name=self.slug, canonical_site=self.site)
		with patch.object(backups, "_live_tenants", return_value=[tenant]), patch("stemic_control.alerts.notify_admins") as alert:
			self.assertEqual(backups.watchdog(), [])  # nightly backups have not started yet
			self.set_settings(last_nightly_run=frappe.utils.nowdate())
			self.assertEqual(backups.watchdog(), [self.slug])
			self.assertIn(f"No backup of {self.site}", alert.call_args.args[0])
			self.take_backup()
			self.assertEqual(backups.watchdog(), [])

	def test_restore_guards(self):
		name = self.take_backup()
		with patch.object(frappe, "enqueue"):
			self.assertRaises(frappe.ValidationError, backups.request_restore, name, "wrong.localhost")
			other = "bk-" + frappe.generate_hash(length=6).lower()
			api.register_tenant("Other School", other, "head@other.test")
			frappe.db.set_value("SaaS Backup", name, "site", f"{other}.localhost")
			self.assertRaises(frappe.ValidationError, backups.request_restore, name, self.site)  # not its own backup
		self.assertRaises(frappe.ValidationError, site_runtime.run_operation, self.slug, "Restore")  # never from the dialog

	def _restore(self, fail_on=None):
		name = self.take_backup(now_datetime() - dt.timedelta(days=1))
		with patch.object(frappe, "enqueue"):
			op = backups.request_restore(name, self.site.upper())["operation"]
		calls = []
		safety_output = self.fake_files(now_datetime())

		def cli(*args, **kw):
			calls.append(args[2:4])
			if fail_on and args[2] == fail_on:
				raise provisioner.ProvisioningError(f"{fail_on} failed: pw-secret leaked?")
			return safety_output if args[2] == "backup" else "ok"

		with patch.object(provisioner, "_frappe_cli", side_effect=cli), \
				patch.object(provisioner, "_root_args", return_value=["--db-root-username", "root", "--db-root-password", "pw-secret"]), \
				patch.object(site_runtime, "_set", side_effect=lambda o, v: frappe.db.set_value("SaaS Site Operation", o, v)), \
				patch("stemic_control.alerts.notify_admins") as alert, patch.object(frappe, "sendmail") as mail:
			status = backups.perform_restore(op)
		return op, status, [c[0] if c[0] != "set-maintenance-mode" else f"maintenance {c[1]}" for c in calls], alert, mail

	def test_restore_runs_in_order(self):
		op, status, steps, alert, mail = self._restore()
		self.assertEqual(status, "Succeeded")
		self.assertEqual(steps, ["backup", "maintenance on", "restore", "migrate", "maintenance off"])
		safety = frappe.get_all("SaaS Backup", filters={"site": self.site, "kind": "Before restore"}, fields=["pinned"])
		self.assertEqual([s.pinned for s in safety], [1])
		self.assertEqual(frappe.db.get_value("SaaS Site Operation", op, "status"), "Succeeded")
		self.assertEqual(mail.call_args.kwargs["recipients"], ["head@backup.test"])

	def test_restore_failure_turns_maintenance_off(self):
		op, status, steps, alert, _mail = self._restore(fail_on="restore")
		self.assertEqual(status, "Failed")
		self.assertEqual(steps[-1], "maintenance off")
		row = frappe.db.get_value("SaaS Site Operation", op, ["status", "output", "summary"], as_dict=True)
		self.assertEqual(row.status, "Failed")
		self.assertNotIn("pw-secret", (row.output or "") + (row.summary or ""))
		self.assertIn("Restore of", alert.call_args.args[0])

	def test_list_download_pin(self):
		name = self.take_backup()
		rows = backups.list_backups(self.slug)
		self.assertEqual(rows[0].name, name)
		self.assertEqual(backups.toggle_pin(name), {"pinned": 1})
		backups.download(name, "database")
		self.assertEqual(frappe.local.response.type, "download")
		self.assertTrue(frappe.local.response.filecontent)
		frappe.local.response.pop("filecontent", None)
		# a backup taken by hand on the server shows up too
		self.fake_files(now_datetime() - dt.timedelta(days=3))
		kinds = [r.kind for r in backups.list_backups(self.slug)]
		self.assertIn("Found on server", kinds)

	def test_admin_only(self):
		email = "not.admin@backup.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Not Admin", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		for call in (lambda: backups.list_backups(self.slug), backups.test_destination, backups.backup_all_now,
					 lambda: backups.request_restore("BKP-00001", self.site)):
			self.assertRaises(frappe.PermissionError, call)
