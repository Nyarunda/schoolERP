"""A school's web pages (parent portal, login) and emails carry Stemic's name, not ERPNext's."""

import frappe

from school_erp.tests.test_integration import TestCase


class TestBranding(TestCase):
    def test_web_pages(self):
        from frappe.website.doctype.website_settings.website_settings import get_website_settings

        ctx = get_website_settings()
        self.assertIn("Stemic Technologies", ctx.footer_powered)
        self.assertIn("https://stemic.cloud", ctx.footer_powered)
        self.assertEqual(ctx.favicon, "/assets/school_erp/images/stemic-favicon.svg")
        self.assertNotIn("erpnext", ctx.splash_image)

    def test_email_footer(self):
        from frappe.email.email_body import get_footer

        footer = get_footer(None, "")
        self.assertNotIn("ERPNext", footer)
        if not frappe.db.get_default("disable_standard_email_footer"):
            self.assertIn("Sent via", footer)
            self.assertIn("Stemic Technologies", footer)
