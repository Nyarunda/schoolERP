"""The admin site's web pages and emails carry Stemic's name, not ERPNext's.
bench --site <site> run-tests --module stemic_control.tests.test_branding"""

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase


class TestBranding(TestCase):
    def test_web_pages(self):
        from frappe.website.doctype.website_settings.website_settings import get_website_settings

        self.assertIn("stemic_control.branding.website_context", frappe.get_hooks("update_website_context"))
        ctx = get_website_settings()
        for method in frappe.get_hooks("update_website_context"):  # as Frappe applies them to every web page
            ctx.update(frappe.get_attr(method)(ctx) or {})
        self.assertIn("Stemic Technologies", ctx.footer_powered)
        self.assertEqual(ctx.favicon, "/assets/stemic_control/images/stemic-favicon.svg")
        self.assertNotIn("erpnext", ctx.splash_image)

    def test_email_footer(self):
        from frappe.email.email_body import get_footer

        footer = get_footer(None, "")
        self.assertNotIn("ERPNext", footer)
        if not frappe.db.get_default("disable_standard_email_footer"):
            self.assertIn("Stemic Technologies", footer)
