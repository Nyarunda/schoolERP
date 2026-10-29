"""School Viewer: reads everything the school has licensed, changes nothing.
bench --site <site> run-tests --module school_erp.tests.test_viewer"""

import frappe

from school_erp.setup import viewer
from school_erp.tests.test_integration import ALL_MODULES, TestCase, set_license, setup_school

MODIFY = ("write", "create", "delete", "submit", "cancel", "amend")


class TestSchoolViewer(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		viewer.setup()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.viewer = self.user("School Viewer")

	def tearDown(self):
		frappe.set_user("Administrator")
		set_license(ALL_MODULES)

	def user(self, *roles):
		email = f"viewer-{frappe.generate_hash(length=6)}@viewer.test"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Viewer", "send_welcome_email": 0,
						"roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)
		return email

	def school_doctypes(self):
		return frappe.get_all("DocType", filters={"module": "School", "istable": 0}, pluck="name")

	def test_reads_every_school_doctype_and_changes_none(self):
		for doctype in self.school_doctypes():
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.has_permission(doctype, "read", user=self.viewer), f"cannot read {doctype}")
				for ptype in MODIFY:
					self.assertFalse(frappe.has_permission(doctype, ptype, user=self.viewer), f"can {ptype} {doctype}")

	def test_reads_the_finance_and_stores_screens_and_changes_none(self):
		for doctype in viewer.ERP_DOCTYPES:
			if not frappe.db.exists("DocType", doctype):
				continue
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.has_permission(doctype, "read", user=self.viewer), f"cannot read {doctype}")
				for ptype in MODIFY:
					self.assertFalse(frappe.has_permission(doctype, ptype, user=self.viewer), f"can {ptype} {doctype}")

	def test_runs_school_and_financial_reports(self):
		frappe.set_user(self.viewer)
		school_reports = frappe.get_all("Report", filters={"module": "School"}, pluck="name")
		self.assertTrue(school_reports)
		for report in [*school_reports, *[r for r in viewer.ERP_REPORTS if frappe.db.exists("Report", r)]]:
			with self.subTest(report=report):
				self.assertTrue(frappe.get_doc("Report", report).is_permitted(), f"cannot run {report}")

	def test_a_real_change_is_refused(self):
		student = frappe.get_doc({"doctype": "Student", "first_name": "view", "last_name": "test", "stream": "Grade 4 Test"}).insert()
		frappe.set_user(self.viewer)
		doc = frappe.get_doc("Student", student.name)  # reading works
		doc.first_name = "changed"
		self.assertRaises(frappe.PermissionError, doc.save)
		self.assertRaises(frappe.PermissionError, frappe.get_doc({"doctype": "Student", "first_name": "new", "last_name": "one",
																	"stream": "Grade 4 Test"}).insert)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Student", student.name)

	def test_sees_everyones_leave_but_staff_viewer_edits_only_their_own(self):
		from school_erp import permissions

		self.assertEqual(permissions.leave_query(self.viewer), "")  # every row in the list
		both = self.user("School Viewer", "Staff")
		other = frappe._dict(doctype="Leave Application", staff_member="STF-OTHER", approver="x@y", owner="x@y", reliever=None,
							 is_new=lambda: False)
		self.assertTrue(permissions.leave_has_permission(other, "read", both))
		self.assertFalse(permissions.leave_has_permission(other, "write", both))  # reading only, never a change

	def test_what_is_not_licensed_stays_hidden(self):
		route = frappe.get_doc("Transport Route", "_Test Route") if frappe.db.exists("Transport Route", "_Test Route") else \
			frappe.get_all("Transport Route", limit=1, pluck="name")
		route = route.name if hasattr(route, "name") else (route[0] if route else None)
		self.assertTrue(route, "the school test data has a transport route")
		set_license(["fees"])
		frappe.set_user(self.viewer)
		self.assertEqual(frappe.get_list("Transport Route", pluck="name"), [])  # lists come back empty
		self.assertFalse(frappe.has_permission("Transport Route", "read", doc=frappe.get_doc("Transport Route", route), user=self.viewer))
