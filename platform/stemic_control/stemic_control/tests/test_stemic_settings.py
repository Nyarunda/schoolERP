"""Stemic Settings: one seller (also for eTIMS), checked KRA PIN and colours, branding in every email and SMS, and the
email preview. bench --site <site> run-tests --module stemic_control.tests.test_stemic_settings"""

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import communications


class TestStemicSettings(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for doctype in ("Stemic Settings", "Stemic Tax Settings"):
            frappe.clear_document_cache(doctype, doctype)

    def save(self, **values):
        s = frappe.get_doc("Stemic Settings")
        s.update(values)
        s.save()
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
        return s

    def test_a_bad_kra_pin_is_refused_and_a_good_one_tidied(self):
        self.assertRaises(frappe.ValidationError, self.save, seller_pin="12345")
        self.assertEqual(self.save(seller_pin=" p051234567x ").seller_pin, "P051234567X")

    def test_the_seller_is_entered_once_and_etims_follows_it(self):
        self.save(seller_name="Stemic Schools Ltd", seller_pin="P051234567X")
        tax = frappe.db.get_singles_dict("Stemic Tax Settings")
        self.assertEqual((tax.seller_name, tax.seller_pin), ("Stemic Schools Ltd", "P051234567X"))
        doc = frappe.get_doc("Stemic Tax Settings")
        doc.seller_name = "Something Else"
        doc.save()  # Tax Settings takes the seller from Stemic Settings
        self.assertEqual(frappe.db.get_single_value("Stemic Tax Settings", "seller_name"), "Stemic Schools Ltd")

    def test_colours_must_be_hex(self):
        self.assertRaises(frappe.ValidationError, self.save, brand_color="navy")
        self.save(brand_color="#0a2540", accent_color="#2e7d32")

    def test_branding_reaches_emails_and_sms(self):
        self.save(brand_name="Acme Learning", brand_color="#0a2540", accent_color="#2e7d32", support_phone="+254 711 000 111")
        html = communications.email_html("Hello", "Intro", [("A", "B")], button=("Go", "https://x.example"))
        self.assertIn("#0a2540", html)  # the header band
        self.assertIn("#2e7d32", html)  # the button
        self.assertIn("Acme", html)
        inv = frappe._dict(name="SINV-1", tenant="t", school_name="Greenfield", plan="Standard", period_start="2026-01-01",
                           period_end="2026-12-31", total=1000, discount_amount=0, outstanding=1000, currency="KES",
                           due_date="2026-01-15")
        subject, html, sms = communications.render_invoice("Invoice Issued", inv)
        self.assertTrue(sms.startswith("Acme Learning: invoice SINV-1"))
        self.assertIn("Acme Learning", subject)
        self.assertIn("+254 711 000 111", html)  # how to reach support

    def test_every_preview_builds_and_sends_nothing(self):
        self.save(payment_instructions="Paybill 123456, Account {invoice}")
        for event in communications.PREVIEWS:
            with self.subTest(event=event):
                p = communications.preview(event)
                self.assertTrue(p["subject"] and p["html"] and p["sms"])
        self.assertIn("Paybill 123456, Account SINV-2026-00012", communications.preview("Invoice Issued")["html"])
        self.assertIn("Set your password", communications.preview("Welcome")["html"])
        self.assertFalse(frappe.db.exists("Email Queue", {"message": ("like", "%greenfield%")}))

    def test_previews_are_for_platform_admins(self):
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, communications.preview, "Welcome")


class TestSettingsDefaultsAfterUpgrade(TestCase):
    def test_new_fields_get_their_defaults_once(self):
        """An existing settings record gets defaults for fields an upgrade added; values already chosen are kept."""
        from stemic_control.setup import fill_new_settings_defaults

        frappe.db.delete("Singles", {"doctype": "Stemic Settings", "field": ("in", ["keep_daily", "nightly_backups", "watch_schools"])})
        frappe.db.set_single_value("Stemic Settings", "keep_weekly", 2)
        fill_new_settings_defaults()
        get = lambda f: frappe.db.get_single_value("Stemic Settings", f)
        self.assertEqual((get("keep_daily"), get("nightly_backups"), get("watch_schools")), (7, 1, 1))
        self.assertEqual(get("keep_weekly"), 2)  # the operator's own value stays
