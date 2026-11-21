"""Deleting a school from the Control Center (specs/features/delete-school).
bench --site <site> run-tests --module stemic_control.tests.test_delete_school"""

import os
from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

try:
	from frappe.tests import IntegrationTestCase as TestCase
except ImportError:  # older Frappe
	from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, backups, billing, deletion, provisioner, site_runtime


class TestDeleteSchool(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
		self._conf.start()
		self.slug = "del-" + frappe.generate_hash(length=6).lower()
		self.site = f"{self.slug}.localhost"
		api.register_tenant("Leaving Academy", self.slug, "head@leaving.test")
		frappe.db.set_value("SaaS Tenant", self.slug, {"canonical_site": self.site, "status": "Active"})
		self.real = site_runtime._site_dir(frappe.local.site)
		self._dir = patch.object(site_runtime, "_site_dir", side_effect=lambda s: self.real if s == self.site else f"/nonexistent/{s}")
		self._dir.start()
		self._suspend = patch("stemic_control.suspension.apply", return_value=self.site)
		self._suspend.start()
		self.made = []

	def tearDown(self):
		for p in self.made:
			if os.path.isfile(p):
				os.unlink(p)
		self._suspend.stop()
		self._dir.stop()
		self._conf.stop()
		frappe.set_user("Administrator")

	# ------------------------------------------------------------------ helpers
	def schedule(self):
		return deletion.schedule(self.slug, f"DELETE {self.slug}", "Closed")["deletion"]

	def make_due(self, name):
		frappe.db.set_value("SaaS Deletion", name, "scheduled_for", nowdate())

	def money(self):
		plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Del " + frappe.generate_hash(length=5), "enabled": 1,
							   "monthly_price": 1000, "student_limit": 100, "modules": "[]"}).insert().name
		sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.slug, "plan": plan, "starts_on": nowdate(),
							  "ends_on": add_days(nowdate(), 10)}).insert().name
		inv = billing.create_invoice(sub, months=1)
		pay = billing.record_payment(inv, 1000, "M-Pesa", "Q" + frappe.generate_hash(length=8).upper())["payment"]
		return inv, pay

	def backup_output(self):
		stamp = now_datetime().strftime("%Y%m%d_%H%M%S")
		folder = os.path.join(self.real, "private", "backups")
		os.makedirs(folder, exist_ok=True)
		base = os.path.join(folder, f"{stamp}-{self.slug.replace('-', '_')}")
		paths = {"Database": base + "-database.sql.gz", "Public": base + "-files.tar", "Private": base + "-private-files.tar"}
		for p in paths.values():
			with open(p, "w") as f:
				f.write("x")
			self.made.append(p)
		return "\n".join(f"{k:<8}: {v} 1.0KiB" for k, v in paths.items())

	def run_deletion(self, name, drop=None):
		"""perform() with the CLI and the drop mocked (the site folder here is the test site's own)."""
		out = self.backup_output()
		calls = []
		with patch.object(provisioner, "_frappe_cli", side_effect=lambda *a, **k: calls.append(a) or out), \
				patch.object(provisioner, "_root_args", return_value=["--db-root-username", "root", "--db-root-password", "pw-secret"]), \
				patch.object(deletion, "_drop", side_effect=drop or (lambda site, cli: calls.append(("drop", site)))), \
				patch.object(deletion, "_final_dir", return_value=os.path.join(self.real, "private", "final-test")), \
				patch("stemic_control.alerts.notify_admins") as alert:
			status = deletion.perform(name)
		return status, calls, alert

	# ------------------------------------------------------------------ tests
	def test_preview(self):
		self.money()
		p = deletion.preview(self.slug)
		self.assertEqual((p["invoices"], p["payments"], p["tax_records"]), (1, 1, 0))
		self.assertEqual(p["confirm_words"], f"DELETE {self.slug}")

	def test_schedule_needs_typed_confirmation(self):
		self.assertRaises(frappe.ValidationError, deletion.schedule, self.slug, "delete")
		self.assertRaises(frappe.ValidationError, deletion.schedule, self.slug, f"DELETE {self.slug}x")

	def test_schedule_suspends(self):
		name = self.schedule()
		d = frappe.get_doc("SaaS Deletion", name)
		self.assertEqual((d.status, getdate(d.scheduled_for), d.previous_status), ("Scheduled", getdate(add_days(nowdate(), 7)), "Active"))
		self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Suspended")
		self.assertRaises(frappe.ValidationError, self.schedule)  # not twice

	def test_cancel_restores(self):
		name = self.schedule()
		deletion.cancel(self.slug)
		self.assertEqual(frappe.db.get_value("SaaS Deletion", name, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Active")

	def test_not_before_grace(self):
		name = self.schedule()
		self.assertRaises(frappe.ValidationError, deletion.delete_now, name)
		self.make_due(name)
		with patch.object(frappe, "enqueue") as enqueue:
			self.assertEqual(deletion.delete_now(name)["status"], "Queued")
		self.assertEqual(enqueue.call_args.kwargs["deletion"], name)

	def test_full_deletion(self):
		inv, pay = self.money()
		frappe.get_doc({"doctype": "SaaS Domain", "tenant": self.slug, "hostname": f"{self.slug}.example.org",
						"domain_type": "Custom Domain"}).insert(ignore_permissions=True)
		name = self.schedule()
		self.make_due(name)
		status, calls, _alert = self.run_deletion(name)
		self.assertEqual(status, "Done", frappe.db.get_value("SaaS Deletion", name, "error"))
		self.assertIn(("drop", self.site), calls)
		self.assertFalse(frappe.db.exists("SaaS Tenant", self.slug))
		for dt, filters in (("SaaS Invoice", {"name": inv}), ("SaaS Payment", {"name": pay}), ("SaaS Domain", {"tenant": self.slug}),
							("SaaS Subscription", {"tenant": self.slug}), ("SaaS Site Operation", {"tenant": self.slug})):
			self.assertFalse(frappe.db.exists(dt, filters), dt)
		d = frappe.get_doc("SaaS Deletion", name)
		final = frappe.get_doc("SaaS Backup", d.final_backup)
		self.assertEqual((final.kind, final.tenant, final.school_name), ("Final copy", None, "Leaving Academy"))
		self.assertEqual(getdate(final.delete_after), getdate(add_days(nowdate(), 90)))
		self.assertTrue(all(os.path.isfile(final.get(f)) for f in ("database_file", "public_file")))  # kept outside the site
		self.made += [final.get(f) for f in backups.FILE_FIELDS if final.get(f)]
		self.assertIn("invoices: 1", d.removed)
		self.assertNotIn("pw-secret", (d.removed or "") + (d.kept or ""))

	def test_tax_records_kept(self):
		from stemic_control import etims

		inv, pay = self.money()
		frappe.get_doc({"doctype": "SaaS Tax Profile", "tenant": self.slug, "seller_pin": "p051234567x", "seller_name": "Leaving Academy",
						"branch_id": "00", "integration_mode": "Manual", "enabled": 1, "default_tax_treatment": "Exempt"}).insert()
		tax = etims.prepare_invoice(tenant=self.slug, external_invoice_no="INV-" + frappe.generate_hash(length=6), buyer_name="Leaving Academy",
									net_amount="1000", vat_amount="0", total_amount="1000", tax_treatment="Exempt")["name"]
		frappe.db.set_value("SaaS eTIMS Invoice", tax, {"saas_invoice": inv, "status": "Submitted"})
		name = self.schedule()
		self.make_due(name)
		status, _calls, _alert = self.run_deletion(name)
		self.assertEqual(status, "Done", frappe.db.get_value("SaaS Deletion", name, "error"))
		self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Deleted")
		self.assertTrue(frappe.db.exists("SaaS Invoice", inv) and frappe.db.exists("SaaS Payment", pay))
		self.assertTrue(frappe.db.exists("SaaS eTIMS Invoice", tax))
		self.assertIn("with KRA", frappe.db.get_value("SaaS Deletion", name, "kept"))

	def test_failure_and_retry(self):
		name = self.schedule()
		self.make_due(name)

		def broken(site, cli):
			raise provisioner.ProvisioningError("drop failed: pw-secret")

		status, _calls, alert = self.run_deletion(name, drop=broken)
		self.assertEqual(status, "Failed")
		d = frappe.get_doc("SaaS Deletion", name)
		self.assertNotIn("pw-secret", d.error)
		self.assertTrue(frappe.db.exists("SaaS Tenant", self.slug))
		self.assertIn("failed", alert.call_args.args[0])
		with patch.object(frappe, "enqueue"):
			deletion.delete_now(name)  # Retry
		status, _calls, _alert = self.run_deletion(name)
		self.assertEqual(status, "Done", frappe.db.get_value("SaaS Deletion", name, "error"))
		self.assertFalse(frappe.db.exists("SaaS Tenant", self.slug))

	def test_final_copy_expires(self):
		name = self.schedule()
		self.make_due(name)
		self.run_deletion(name)
		final = frappe.db.get_value("SaaS Deletion", name, "final_backup")
		frappe.db.set_value("SaaS Backup", final, "delete_after", add_days(nowdate(), -1))
		with patch.object(deletion, "_final_dir", return_value=os.path.join(self.real, "private", "final-test")):
			self.assertEqual(backups.prune_final_copies(), 1)
		self.assertEqual(frappe.db.get_value("SaaS Backup", final, "status"), "Removed")

	def test_reminder(self):
		name = self.schedule()
		frappe.db.set_value("SaaS Deletion", name, "scheduled_for", add_days(nowdate(), 1))
		with patch("stemic_control.alerts.notify_admins") as alert, patch.object(deletion, "perform"):
			deletion.daily()
			deletion.daily()
		self.assertEqual([c.args[0] for c in alert.call_args_list], ["Leaving Academy will be deleted tomorrow"])

	def test_drop_removes_archived_copy(self):
		bench = os.path.join(self.real, "private", "bench-test")
		os.makedirs(os.path.join(bench, "archived_sites", self.site), exist_ok=True)
		os.makedirs(os.path.join(bench, "archived_sites", "other.localhost"), exist_ok=True)
		calls = []
		with patch.object(provisioner, "_bench", return_value=bench), \
				patch.object(provisioner, "_root_args", return_value=["--db-root-password", "x"]):
			deletion._drop(self.site, lambda *a, **k: calls.append(a))
		self.assertEqual(calls[0][0], "drop-site")
		self.assertFalse(os.path.exists(os.path.join(bench, "archived_sites", self.site)))
		self.assertTrue(os.path.exists(os.path.join(bench, "archived_sites", "other.localhost")))  # only this school's
		import shutil

		shutil.rmtree(bench, ignore_errors=True)

	def test_admin_only(self):
		email = "not.admin@delete.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Not Admin", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(email)
		for call in (lambda: deletion.preview(self.slug), lambda: deletion.schedule(self.slug, f"DELETE {self.slug}"),
					 lambda: deletion.cancel(self.slug), lambda: deletion.delete_now("DEL-00001")):
			self.assertRaises(frappe.PermissionError, call)
