"""The school's first administrator, created by the Control Center when it builds the site.
bench --site <site> run-tests --module school_erp.tests.test_first_admin"""

import frappe

from school_erp.setup import first_admin
from school_erp.tests.test_integration import TestCase


class TestFirstAdmin(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.email = f"head-{frappe.generate_hash(length=6)}@first.test"

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("User", self.email):
			frappe.delete_doc("User", self.email, force=True, ignore_permissions=True)
		frappe.db.commit()  # create() commits, so its user outlives the test transaction

	def test_creates_the_admin_with_a_one_time_link(self):
		out = first_admin.create(self.email.upper(), "Greenfield Admin")
		self.assertEqual(out["user"], self.email)
		self.assertIn("/update-password?key=", out["link"])
		user = frappe.get_doc("User", self.email)
		self.assertEqual((user.first_name, user.user_type, user.enabled), ("Greenfield", "System User", 1))
		self.assertTrue({"School Admin", "System Manager"} <= {r.role for r in user.roles})
		self.assertTrue(user.reset_password_key)  # stored hashed; the link carries the key itself
		self.assertNotIn(user.reset_password_key, out["link"])
		self.assertGreaterEqual(frappe.get_system_settings("reset_password_link_expiry_duration"), 24 * 3600)

	def test_running_again_reuses_the_user_and_replaces_the_link(self):
		first = first_admin.create(self.email)
		second = first_admin.create(self.email)
		self.assertEqual(first["user"], second["user"])
		self.assertNotEqual(first["link"], second["link"])
		self.assertEqual(frappe.db.count("User", {"name": self.email}), 1)

	def test_refuses_a_bad_email(self):
		self.assertRaises(frappe.ValidationError, first_admin.create, "not-an-email")
