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
		# CI installs apps with --skip-assets, so there is no assets.json and Frappe's print view cannot look up
		# print.bundle.css. Treat that as "no bundles" so the real print format still renders.
		real_assets = frappe.utils.get_assets_json
		self._assets = patch("frappe.utils.get_assets_json", side_effect=lambda: real_assets() or {})
		self._assets.start()

	def tearDown(self):
		self._assets.stop()
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
		self.assertRaises(frappe.PermissionError, dv.issue, "Student", student)  # not a verifiable document: nobody may issue it
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

	def test_records_only_come_from_issuing_and_are_never_deleted(self):
		fp = self.posted_payment(self.make_student().name)
		forged = frappe.get_doc({"doctype": "Verified Document", "verification_code": "F" * 43, "document_type": "Fee Payment",
								 "document_name": fp.name, "pdf_hash": "0" * 64, "status": "Valid"})
		self.assertRaises(frappe.PermissionError, forged.insert, ignore_permissions=True)

		issued = dv.issue("Fee Payment", fp.name)
		doc = frappe.get_doc("Verified Document", issued["code"])
		doc.pdf_hash = "0" * 64  # an edit outside the issuing service
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Verified Document", issued["code"], force=True)
		self.assertEqual(dv.verify(issued["code"])["status"], "Valid")

	def test_finance_and_academic_staff_issue_only_their_documents(self):
		fp = self.posted_payment(self.make_student().name)
		frappe.set_user(self.staff("Head Teacher"))
		self.assertRaises(frappe.PermissionError, dv.issue, "Fee Payment", fp.name)
		frappe.set_user(self.staff("Bursar"))
		self.assertTrue(dv.issue("Fee Payment", fp.name)["code"])
		self.assertRaises(frappe.PermissionError, dv.issue, "Report Card", "anything")

	def test_reissued_statement_for_the_same_period_revokes_the_old_one(self):
		student = self.make_student().name
		self.posted_payment(student)
		first = dv.issue_statement(student)
		second = dv.issue_statement(student)
		self.assertEqual(dv.verify(first["code"])["status"], "Revoked")
		self.assertEqual(dv.verify(second["code"])["status"], "Valid")
