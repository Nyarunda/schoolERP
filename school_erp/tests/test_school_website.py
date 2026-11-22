"""The school's public website: homepage at "/", branded sign-in, navbar brand.
bench --site <site> run-tests --module school_erp.tests.test_school_website"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate, set_request
from frappe.website.serve import get_response
from frappe.website.utils import clear_website_cache

from school_erp import website
from school_erp.tests.test_integration import TestCase, setup_school


def render(path, user="Guest"):
	"""Render a web page as a browser would. CI's bench has no built assets, so bundle names pass through unhashed."""
	from frappe.utils import jinja_globals

	frappe.set_user(user)
	frappe.cache.delete_key("home_page")
	clear_website_cache()
	set_request(method="GET", path=path)
	with patch.object(jinja_globals, "bundled_asset", lambda path, rtl=None: path):
		response = get_response(path)
	return response.status_code, frappe.safe_decode(response.get_data()), response


class TestSchoolWebsite(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		frappe.set_user("Administrator")
		cls.tag = frappe.generate_hash(length=5)
		frappe.db.set_single_value("School Settings", {"website_home_on": 1, "show_term_dates": 1, "site_color": "#3cbd4d",
													   "site_intro": f"Intro {cls.tag}", "phone": "0711 000 222",
													   "mpesa_account_type": "Paybill", "paybill_number": "123456"})
		today = nowdate()
		cls.notices = {}
		for key, ticked, publish, expiry in (("shown", 1, today, add_days(today, 5)), ("staff", 0, today, add_days(today, 5)),
											 ("old", 1, add_days(today, -20), add_days(today, -10))):
			cls.notices[key] = frappe.get_doc({"doctype": "School Notice", "title": f"WEB {key} {cls.tag}", "audience": "All Staff",
											   "publish_date": publish, "expiry_date": expiry, "show_on_website": ticked,
											   "message": f"<p>Body of {key}</p>"}).insert().name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in cls.notices.values():
			frappe.delete_doc("School Notice", name, force=True, ignore_permissions=True)
		frappe.db.set_single_value("School Settings", {"site_color": "", "site_intro": "", "show_term_dates": 1, "website_home_on": 1})
		frappe.db.commit()
		cls._pub.stop()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_home_page_is_the_school_site(self):
		status, html, _ = render("/")
		self.assertEqual(status, 200)
		self.assertIn('id="school-home"', html)
		self.assertIn("Test School", html)
		self.assertIn(f"Intro {self.tag}", html)
		self.assertIn('data-card="verify"', html)
		self.assertIn("Powered by", html)
		self.assertNotIn("<!-- login.html -->", html)

	def test_cards_follow_the_licence(self):
		with patch.object(website, "_licensed", return_value=False):
			cards = [c[0] for c in website.home_context().cards]
		self.assertEqual(cards, ["fees", "verify", "staff", "contact"])
		with patch.object(website, "_licensed", return_value=True):
			cards = [c[0] for c in website.home_context().cards]
		self.assertIn("parents", cards)
		self.assertIn("apply", cards)

	def test_home_shows_fees(self):
		data = website.home_context()
		self.assertEqual((data.pay["number"], data.pay["kind"]), ("123456", "Paybill"))
		_, html, _ = render("/")
		self.assertIn("123456", html)
		self.assertIn("admission number", html)

	def test_only_website_notices(self):
		titles = [n.title for n in website.home_context().notices]
		self.assertIn(f"WEB shown {self.tag}", titles)
		self.assertNotIn(f"WEB staff {self.tag}", titles)
		self.assertNotIn(f"WEB old {self.tag}", titles)

	def test_term_dates(self):
		data = website.home_context()
		self.assertTrue(data.terms)
		self.assertTrue(all(t.opens for t in data.terms))
		self.assertEqual(len({t.school_year for t in data.terms}), 1)  # one school year
		frappe.db.set_single_value("School Settings", "show_term_dates", 0)
		try:
			self.assertEqual(website.home_context().terms, [])
		finally:
			frappe.db.set_single_value("School Settings", "show_term_dates", 1)

	def test_switched_off_goes_to_login(self):
		frappe.db.set_single_value("School Settings", "website_home_on", 0)
		try:
			status, _, response = render("/")
			self.assertIn(status, (301, 302))
			self.assertTrue(response.headers.get("Location", "").endswith("/login"))
		finally:
			frappe.db.set_single_value("School Settings", "website_home_on", 1)

	def test_login_is_branded(self):
		status, html, _ = render("/login")
		self.assertEqual(status, 200)
		self.assertIn('class="ss-login"', html)
		self.assertIn("Test School", html)
		self.assertIn("password the school sent you by SMS", html)
		# Frappe's own form and script are still there
		for text in ("<!-- login.html -->", 'id="login_email"', 'id="login_password"', "#forgot", "// login.js"):
			self.assertIn(text, html)

	def test_navbar_brand(self):
		values = website.update_context(frappe._dict())
		self.assertIn("Test School", values["brand_html"])
		self.assertEqual(values["school_site"].name, "Test School")
		self.assertNotEqual(values["school_site"].color, "#3cbd4d")  # darkened to stay readable

	def test_signed_in_button(self):
		frappe.set_user("Administrator")
		self.assertEqual(website.account_button()["label"], "Open the school system")
		_, html, _ = render("/")
		self.assertIn(">Sign in<", html)

	def test_status_pages_keep_working(self):
		for path in ("/admission-status", "/complaint-status", "/verify"):
			with self.subTest(path=path):
				status, html, _ = render(path)
				self.assertEqual(status, 200)
				self.assertIn("ss-header", html)
