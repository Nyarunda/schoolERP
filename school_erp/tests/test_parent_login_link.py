"""Guardians are linked to parent logins by themselves, in either order (specs/features/auto-link-parent-logins).
bench --site <site> run-tests --module school_erp.tests.test_parent_login_link"""

import random

import frappe

from school_erp.api import portal
from school_erp.tests.test_integration import TestCase, setup_school


def _phone():
	return "07" + "".join(random.choice("0123456789") for _ in range(8))


def _email():
	return f"parent.{frappe.generate_hash(length=8)}@test.school"


class TestParentLoginLink(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.set_user("Administrator")

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")

	def _login(self, email, mobile=None, website=True):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Parent", "mobile_no": mobile,
							"send_welcome_email": 0, "user_type": "Website User" if website else "System User",
							"roles": [] if website else [{"role": "Teacher"}]})  # a desk role makes it staff
		u.insert(ignore_permissions=True)
		return u.name

	def _student(self, email=None, phone=None, user=None):
		return frappe.get_doc({
			"doctype": "Student", "first_name": "Linky", "last_name": frappe.generate_hash(length=5), "stream": "Grade 4 Test",
			"gender": "Female",
			"guardians": [{"guardian_name": "Mama Linky", "relation": "Mother", "mobile_no": phone or _phone(),
						   "email": email, "user": user, "is_primary": 1}],
		}).insert()

	def _guardian_user(self, student):
		return frappe.db.get_value("Student Guardian", {"parent": student.name}, "user")

	def test_guardian_added_after_login(self):
		email = _email()
		user = self._login(email)
		s = self._student(email=email.upper())  # case does not matter
		self.assertEqual(self._guardian_user(s), user)
		self.assertIn("Parent", frappe.get_roles(user))
		self.assertIn(s.name, portal.children_of(user))

	def test_login_created_after_guardian(self):
		phone = _phone()
		s = self._student(phone=phone)
		self.assertFalse(self._guardian_user(s))
		user = self._login(_email(), mobile="+254" + phone[1:])  # stored in another form
		self.assertEqual(self._guardian_user(s), user)
		self.assertIn("Parent", frappe.get_roles(user))

	def test_staff_account_never_linked(self):
		email = _email()
		staff = self._login(email, website=False)
		s = self._student(email=email)
		self.assertFalse(self._guardian_user(s))
		frappe.get_doc("User", staff).save(ignore_permissions=True)
		self.assertFalse(self._guardian_user(s))

	def test_ambiguous_match_left_alone(self):
		email, phone = _email(), _phone()
		self._login(email)
		self._login(_email(), mobile=phone)
		s = self._student(email=email, phone=phone)  # email says one parent, phone another
		self.assertFalse(self._guardian_user(s))

	def test_existing_link_kept(self):
		email = _email()
		first = self._login(email)
		s = self._student(email=email)
		self.assertEqual(self._guardian_user(s), first)
		other = self._login(_email(), mobile=frappe.db.get_value("Student Guardian", {"parent": s.name}, "mobile_no"))
		s.reload()
		s.save()
		self.assertEqual(self._guardian_user(s), first)  # never replaced
		self.assertNotEqual(first, other)

	def test_nothing_linked_without_portal_module(self):
		from unittest.mock import patch

		email = _email()
		self._login(email)
		with patch("school_erp.api.portal._portal_on", return_value=False):
			s = self._student(email=email)
		self.assertFalse(self._guardian_user(s))
