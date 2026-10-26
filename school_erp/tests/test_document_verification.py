"""Verified (QR-stamped) documents against a database: issue, public check, tampering, revocation, permissions.
bench --site <site> run-tests --module school_erp.tests.test_document_verification"""

import hashlib
from unittest.mock import patch

import frappe

from school_erp.api import document_verification as dv
from school_erp.tests.test_integration import ALL_MODULES, TestCase, set_license, setup_school


class TestDocumentVerification(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		# PDF rendering needs the site served over HTTP for its stylesheets; test the HTML that would be rendered
		self.rendered = []
		self._pdf = patch("frappe.utils.pdf.get_pdf", side_effect=self.fake_pdf)
		self._pdf.start()

	def tearDown(self):
		self._pdf.stop()
		frappe.set_user("Administrator")
		set_license(ALL_MODULES)

	def fake_pdf(self, html, *args, **kwargs):
		"""A real one-page PDF whose content depends on the stamped HTML (File insists on a valid PDF)."""
		import io

		from pypdf import PdfWriter

		self.rendered.append(html)
		writer = PdfWriter()
		writer.add_blank_page(100, 100)
		writer.add_metadata({"/Subject": hashlib.sha256(html.encode()).hexdigest()})
		out = io.BytesIO()
		writer.write(out)
		return out.getvalue()

	def make_student(self):
		return frappe.get_doc({
			"doctype": "Student", "first_name": "verify", "last_name": "test", "stream": "Grade 4 Test",
			"guardians": [{"guardian_name": "Grace Test", "relation": "Mother", "mobile_no": "0712345678"}],
		}).insert()

	def posted_payment(self, student):
		fp = frappe.get_doc({"doctype": "Fee Payment", "student": student, "amount": 500,
							 "reference_no": "V" + frappe.generate_hash(length=8)}).insert()
		fp.submit()
		return fp

	def staff(self, role):
		email = f"{role.lower().replace(' ', '-')}-{frappe.generate_hash(length=5)}@verify.test"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": role, "send_welcome_email": 0,
						"roles": [{"role": role}]}).insert(ignore_permissions=True)
		return email

	def pdf(self, issued):
		with open(frappe.get_doc("File", {"file_url": issued["file_url"]}).get_full_path(), "rb") as f:
			return f.read()  # the exact bytes a holder would have

	# ------------------------------------------------------------------
	def test_receipt_check_tampering_and_reissue(self):
		fp = self.posted_payment(self.make_student().name)
		issued = dv.issue("Fee Payment", fp.name)
		pdf = self.pdf(issued)
		self.assertTrue(pdf.startswith(b"%PDF"))
		self.assertIn(issued["code"], self.rendered[-1])  # the stamp carries the code
		self.assertIn('src="data:image/png;base64,', self.rendered[-1])  # and a QR image

		frappe.set_user("Guest")
		state = dv.verify(issued["code"])
		self.assertEqual((state["status"], state["document_type"], state["issuer"]), ("Valid", "Fee Payment", "Test School"))
		self.assertNotIn("document_name", state)  # the public answer names no student or receipt
		self.assertTrue(dv.verify_hash(issued["code"], hashlib.sha256(pdf).hexdigest())["matches"])
		self.assertFalse(dv.verify_hash(issued["code"], hashlib.sha256(pdf + b" ").hexdigest())["matches"])
		self.assertEqual(dv.verify("x" * 40)["status"], "Not Found")
		self.assertEqual(dv.verify("short")["status"], "Not Found")

		frappe.set_user("Administrator")
		again = dv.issue("Fee Payment", fp.name)
		self.assertEqual(dv.verify(issued["code"])["status"], "Revoked")
		self.assertEqual(dv.verify(again["code"])["status"], "Valid")

		fp.reload()
		fp.cancel()  # a cancelled receipt no longer verifies
		self.assertEqual(dv.verify(again["code"])["status"], "Revoked")

	def test_only_staff_issue_and_unposted_receipts_refused(self):
		student = self.make_student().name
		draft = frappe.get_doc({"doctype": "Fee Payment", "student": student, "amount": 100,
								"reference_no": "V" + frappe.generate_hash(length=8)}).insert()
		self.assertRaises(frappe.ValidationError, dv.issue, "Fee Payment", draft.name)
		self.assertRaises(frappe.ValidationError, dv.issue, "Student", student)  # not a verifiable document
		fp = self.posted_payment(student)
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, dv.issue, "Fee Payment", fp.name)

	def test_certificate_approve_lock_issue_revoke(self):
		cert = frappe.get_doc({"doctype": "School Certificate", "student": self.make_student().name,
							   "certificate_type": "Transfer Letter", "issue_date": frappe.utils.nowdate(),
							   "recipient": "Head Teacher", "body": "Confirming enrolment."}).insert()
		self.assertRaises(frappe.ValidationError, dv.issue, "School Certificate", cert.name)  # still Draft
		dv.approve_certificate(cert.name)
		cert.reload()
		cert.body = "Changed after approval"
		self.assertRaises(frappe.PermissionError, cert.save)

		issued = dv.issue("School Certificate", cert.name)
		self.assertEqual(dv.verify(issued["code"])["status"], "Valid")
		self.assertRaises(frappe.ValidationError, dv.revoke_certificate, cert.name, "short")
		dv.revoke_certificate(cert.name, "Issued to the wrong school")
		self.assertEqual(dv.verify(issued["code"])["status"], "Revoked")

	def test_school_admin_can_issue_and_revoke_a_statement(self):
		student = self.make_student().name
		self.posted_payment(student)
		frappe.set_user(self.staff("School Admin"))
		issued = dv.issue_statement(student)
		self.assertEqual(dv.verify(issued["code"])["document_type"], "Fee Statement")
		self.assertEqual(dv.revoke(issued["code"], "Replaced by a corrected statement")["status"], "Revoked")
		self.assertEqual(dv.verify(issued["code"])["status"], "Revoked")

	def test_unlicensed_module_cannot_issue(self):
		student = self.make_student().name
		fp = self.posted_payment(student)
		set_license(["exams"])  # no fees module
		self.assertRaises(frappe.PermissionError, dv.issue, "Fee Payment", fp.name)
		self.assertRaises(frappe.PermissionError, dv.issue_statement, student)
