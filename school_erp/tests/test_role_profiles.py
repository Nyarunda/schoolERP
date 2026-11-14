"""Default job role profiles.
bench --site <site> run-tests --module school_erp.tests.test_role_profiles"""

import frappe

from school_erp.setup import role_profiles
from school_erp.tests.test_integration import TestCase, setup_school


def _user(email, profile=None):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0].title(),
						"send_welcome_email": 0}).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	if profile:
		user.set("role_profiles", [{"role_profile": profile}])
		user.save(ignore_permissions=True)
	return frappe.get_doc("User", email)


class TestRoleProfiles(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		role_profiles.make_role_profiles()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")

	def test_every_profile_exists_with_its_roles(self):
		for name, roles in role_profiles.PROFILES.items():
			self.assertTrue(frappe.db.exists("Role Profile", name), name)
			have = {r.role for r in frappe.get_doc("Role Profile", name).roles}
			self.assertTrue(set(roles) <= have, name)

	def test_make_is_idempotent_and_keeps_school_edits(self):
		doc = frappe.get_doc("Role Profile", "Librarian")
		doc.append("roles", {"role": "Teacher"})
		doc.save(ignore_permissions=True)
		role_profiles.make_role_profiles()
		role_profiles.make_role_profiles()
		roles = [r.role for r in frappe.get_doc("Role Profile", "Librarian").roles]
		self.assertIn("Teacher", roles)  # the school's addition stays
		self.assertEqual(len(roles), len(set(roles)))  # nothing doubled

	def test_head_teacher_profile_opens_students(self):
		user = _user("profile.head@test.school", "Head Teacher")
		roles = set(frappe.get_roles(user.name))
		self.assertTrue({"Head Teacher", "Teacher"} <= roles)
		self.assertTrue(frappe.has_permission("Student", "read", user=user.name))

	def test_bursar_profile_keeps_accounting_roles(self):
		user = _user("profile.bursar@test.school", "Bursar")
		user.save(ignore_permissions=True)  # a second save re-syncs from the profile
		roles = set(frappe.get_roles(user.name))
		self.assertIn("Bursar", roles)
		self.assertIn("Accounts User", roles)

	def test_profile_keeps_earned_roles(self):
		email = "profile.hod@test.school"
		user = _user(email, "Teacher")
		if not frappe.db.exists("Subject", "Role Profile Test Subject"):
			frappe.get_doc({"doctype": "Subject", "subject_name": "Role Profile Test Subject"}).insert(ignore_permissions=True)
		subject = "Role Profile Test Subject"
		old = frappe.db.get_value("Subject", subject, "head_of_department")
		frappe.db.set_value("Subject", subject, "head_of_department", email)
		try:
			user.save(ignore_permissions=True)
			self.assertIn("Head of Department", frappe.get_roles(email))
		finally:
			frappe.db.set_value("Subject", subject, "head_of_department", old)

	def test_board_profile_is_read_only(self):
		user = _user("profile.board@test.school", "Board / Auditor")
		roles = set(frappe.get_roles(user.name))
		self.assertIn("School Viewer", roles)
		self.assertFalse(roles & {"School Admin", "Head Teacher", "Bursar", "Teacher", "Staff"})
		self.assertTrue(frappe.has_permission("Student", "read", user=user.name))
		self.assertFalse(frappe.has_permission("Student", "write", user=user.name))
