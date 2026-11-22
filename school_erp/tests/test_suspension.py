"""A school suspended by Stemic answers every request with "service suspended".
bench --site <site> run-tests --module school_erp.tests.test_suspension"""

import json
import os
import unittest
from unittest.mock import patch

import frappe
from werkzeug.exceptions import HTTPException

from school_erp import suspension


class TestSuspension(unittest.TestCase):
	def request(self, path, accept="text/html", suspended=True, **conf):
		values = {"stemic_suspended": 1 if suspended else 0, **conf}
		with patch.object(suspension, "_site_config", return_value=frappe._dict(values)), \
				patch.object(frappe.local, "request", frappe._dict(path=path), create=True), \
				patch.object(frappe, "get_request_header", side_effect=lambda h: accept if h == "Accept" else None):
			try:
				suspension.check()
			except HTTPException as e:
				return e.response
		return None

	def test_pages_and_the_desk_show_service_suspended(self):
		for path in ("/", "/app", "/login", "/app/fee-payment/new"):
			with self.subTest(path=path):
				response = self.request(path, stemic_suspended_message="Greenfield's service is suspended.",
										stemic_support_email="support@stemicschools.com")
				self.assertEqual(response.status_code, 503)
				page = response.get_data(as_text=True)
				self.assertIn("Service suspended", page)
				self.assertIn("Greenfield", page)
				self.assertIn("s service is suspended.", page)  # the message, escaped
				self.assertIn("support@stemicschools.com", page)

	def test_the_api_refuses_with_json(self):
		for path, accept in (("/api/method/frappe.auth.get_logged_user", "text/html"), ("/app", "application/json")):
			with self.subTest(path=path):
				response = self.request(path, accept)
				self.assertEqual((response.status_code, response.mimetype), (503, "application/json"))
				self.assertEqual(json.loads(response.get_data())["exc_type"], "SchoolSuspended")

	def test_stylesheets_and_images_still_load(self):
		for path in ("/assets/frappe/dist/css/website.bundle.css", "/files/logo.png", "/favicon.ico"):
			with self.subTest(path=path):
				self.assertIsNone(self.request(path))

	def test_a_running_school_is_untouched(self):
		self.assertIsNone(self.request("/app", suspended=False))

	def test_a_change_on_disk_is_seen_at_once(self):
		"""Frappe caches site config for a minute per web worker; the suspension reads the file when it changes."""
		import tempfile

		with tempfile.TemporaryDirectory() as folder, \
				patch.object(suspension, "_config_path", return_value=f"{folder}/site_config.json"):
			path = f"{folder}/site_config.json"
			with open(path, "w") as f:
				json.dump({"stemic_suspended": 0}, f)
			self.assertFalse(suspension.suspended())
			with open(path, "w") as f:
				json.dump({"stemic_suspended": 1}, f)
			os.utime(path, ns=(1, 2))  # a different modified time, as any real write gives
			self.assertTrue(suspension.suspended())

	def test_the_page_shows_why_what_is_owed_how_to_pay_and_who_to_call(self):
		info = {"school": "Greenfield Academy", "brand": "Stemic Schools", "email": "support@stemicschools.com",
				"phone": "+254 711 000 111", "reason": "Unpaid invoice", "invoice": "SINV-2026-00012",
				"amount_due": "KES 114,000.00", "due_date": "15-10-2026", "how_to_pay": "Paybill 123456, Account SINV-2026-00012"}
		response = self.request("/app", stemic_suspension=info)
		page = response.get_data(as_text=True)
		for text in ("Greenfield Academy", "Service suspended", "Unpaid invoice", "KES 114,000.00", "SINV-2026-00012",
					 "Paybill 123456", "mailto:support@stemicschools.com", "tel:+254711000111", "Check again"):
			self.assertIn(text, page)
		api = self.request("/api/method/x", stemic_suspension=info)
		self.assertEqual(json.loads(api.get_data())["amount_due"], "KES 114,000.00")

	def test_nothing_owed_shows_no_amount(self):
		page = self.request("/app", stemic_suspension={"school": "Greenfield Academy", "reason": "Requested by the school"}).get_data(as_text=True)
		self.assertNotIn("Amount due", page)
		self.assertIn("Requested by the school", page)

	def test_parents_see_the_school_and_its_office_first(self):
		school = {"name": "Greenfield Academy", "phone": "0711 222 333", "email": "office@greenfield.ac.ke", "color": "#3cbd4d"}
		page = suspension.page({"school": "Greenfield Academy", "reason": "Unpaid invoice", "amount_due": "KES 114,000.00"},
							   school=school)
		for text in ("The school portal is paused for now", "Your records are safe", "tel:0711222333",
					 "office@greenfield.ac.ke", "For school administrators", "Check again"):
			self.assertIn(text, page)
		# what is owed to Stemic sits inside the administrators' section, after the school's contacts
		self.assertLess(page.index("office@greenfield.ac.ke"), page.index("For school administrators"))
		self.assertLess(page.index("For school administrators"), page.index("KES 114,000.00"))
		self.assertNotIn("#3cbd4d", page)  # too light for white text: a darker shade is used

	def test_the_page_renders_without_the_database(self):
		with patch.object(frappe.db, "get_single_value", side_effect=Exception("no database")):
			page = suspension.page({"brand": "Stemic Schools"}, "Service suspended.", "support@stemicschools.com")
		self.assertIn("The school portal is paused for now", page)
		self.assertIn("support@stemicschools.com", page)
