"""eTIMS preparation against a database: identity, validation, immutability, provider evidence and access.
No real tax authority or provider is contacted: the adapter is a fake module.
bench --site <site> run-tests --module stemic_control.tests.test_etims"""

import sys
import types
from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, etims

ADAPTER = "stemic_control_integrations.fake_provider"


class TestEtims(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
        self._conf.start()
        self.tenant = api.register_tenant("Tax Academy", "tax-" + frappe.generate_hash(length=6).lower(), "head@tax.test")
        frappe.get_doc({"doctype": "SaaS Tax Profile", "tenant": self.tenant, "seller_pin": "p051234567x", "seller_name": "Tax Academy",
                        "branch_id": "00", "integration_mode": "Manual", "enabled": 1, "default_tax_treatment": "Exempt"}).insert()
        self.args = dict(tenant=self.tenant, external_invoice_no="INV-" + frappe.generate_hash(length=6), buyer_name="Grace Parent",
                         net_amount="25000", vat_amount="0", total_amount="25000", tax_treatment="Exempt")

    def tearDown(self):
        self._conf.stop()
        sys.modules.pop("stemic_control_integrations", None)
        sys.modules.pop(ADAPTER, None)
        frappe.set_user("Administrator")

    def provider(self, reply):
        """Install a fake certified-provider adapter that answers `reply`."""
        sys.modules["stemic_control_integrations"] = types.ModuleType("stemic_control_integrations")
        module = types.ModuleType(ADAPTER)
        module.submit = lambda payload: reply
        sys.modules[ADAPTER] = module
        return patch.dict(frappe.local.conf, {"stemic_etims_live_enabled": 1, "stemic_etims_adapter": ADAPTER + ".submit"})

    def pending(self):
        name = etims.prepare_invoice(**self.args)["name"]
        etims.approve_invoice(name)
        frappe.db.set_value("SaaS eTIMS Invoice", name, "status", "Pending Submission")
        return name

    def events(self, name):
        return [e.event_type for e in etims.invoice_history(name)]

    # ------------------------------------------------------------------
    def test_same_source_is_one_record_and_changes_are_refused(self):
        first = etims.prepare_invoice(**self.args)
        self.assertEqual(etims.prepare_invoice(**self.args), first)
        self.assertRaises(frappe.ValidationError, etims.prepare_invoice, **{**self.args, "net_amount": "26000", "total_amount": "26000"})
        self.assertIn("Prepared", self.events(first["name"]))  # who captured it and when is on record

    def test_amounts_pins_and_sellers_are_checked(self):
        bad = [
            {"vat_amount": "100", "total_amount": "25100"},  # exempt with VAT
            {"total_amount": "1"},  # total is not net + tax
            {"buyer_pin": "123"},
            {"net_amount": "1.001", "total_amount": "1.001"},
            {"seller_scope": "Stemic Platform", "subscription": "x"},  # platform seller not set up
        ]
        for n, change in enumerate(bad):
            self.assertRaises(frappe.ValidationError, etims.prepare_invoice,
                              **{**self.args, "external_invoice_no": f"BAD-{n}", **change})

    def test_records_cannot_be_edited_or_deleted(self):
        name = etims.prepare_invoice(**self.args)["name"]
        doc = frappe.get_doc("SaaS eTIMS Invoice", name)
        doc.total_amount = 1
        self.assertRaises(frappe.PermissionError, doc.save)
        self.assertRaises(frappe.PermissionError, frappe.delete_doc, "SaaS eTIMS Invoice", name, force=True)
        forged = frappe.get_doc({"doctype": "SaaS eTIMS Invoice", "invoice_key": "ETI-FORGED", "tenant": self.tenant, "status": "Submitted"})
        self.assertRaises(frappe.PermissionError, forged.insert, ignore_permissions=True)

    def test_nothing_is_sent_without_a_configured_provider(self):
        name = etims.prepare_invoice(**self.args)["name"]
        self.assertEqual(etims.approve_invoice(name)["status"], "Ready")
        self.assertRaises(frappe.ValidationError, etims.queue_submission, name)
        self.assertEqual(frappe.db.get_value("SaaS eTIMS Invoice", name, "status"), "Ready")

    def test_provider_answers_count_only_with_verified_evidence(self):
        name = self.pending()
        with self.provider({"status": "accepted", "provider_reference": "P1", "kra_invoice_number": "K1"}):
            self.assertRaises(frappe.ValidationError, etims.submit_queued, name)  # accepted, but no evidence
        with self.provider({"status": "rejected", "reason": "spoofed"}):
            self.assertEqual(etims.submit_queued(name)["status"], "Pending Submission")  # unverified rejection
        self.assertIn("Provider response unverified", self.events(name))
        good = {"status": "accepted", "provider_reference": "P1", "kra_invoice_number": "K1",
                "verification_evidence": "signed receipt", "signature_verified": True}
        with self.provider(good):
            self.assertEqual(etims.submit_queued(name)["status"], "Submitted")
        self.assertEqual(frappe.db.get_value("SaaS eTIMS Invoice", name, "kra_invoice_number"), "K1")

    def test_verified_rejection_is_recorded(self):
        name = self.pending()
        with self.provider({"status": "rejected", "reason": "Invalid PIN", "signature_verified": True}):
            self.assertEqual(etims.submit_queued(name)["status"], "Rejected")
        self.assertEqual(frappe.db.get_value("SaaS eTIMS Invoice", name, "last_error"), "Invalid PIN")

    def test_a_profile_can_be_drafted_before_the_pin_arrives(self):
        other = api.register_tenant("Pin Pending School", "pin-" + frappe.generate_hash(length=6).lower(), "head@pin.test")
        profile = frappe.get_doc({"doctype": "SaaS Tax Profile", "tenant": other, "seller_name": "Pin Pending School", "integration_mode": "Manual",
                                  "default_tax_treatment": "Review Required"}).insert()
        profile.enabled = 1
        profile.branch_id = "00"
        self.assertRaises(frappe.ValidationError, profile.save)  # but cannot be enabled without a valid PIN

    def test_a_new_profile_needs_only_the_school_and_its_name(self):
        other = api.register_tenant("Form School", "form-" + frappe.generate_hash(length=6).lower(), "head@form.test")
        profile = frappe.get_doc({"doctype": "SaaS Tax Profile", "tenant": other}).insert()  # what the New form sends
        self.assertEqual((profile.seller_name, profile.integration_mode, profile.default_tax_treatment),
                         ("Form School", "Manual", "Review Required"))
        profile.seller_pin = " p05 1234567x "
        profile.save()
        self.assertEqual(profile.seller_pin, "P051234567X")  # typed with spaces and in lower case
        profile.seller_pin = "P05123456"
        self.assertRaises(frappe.ValidationError, profile.save)
        profile.reload()
        profile.enabled = 1
        self.assertRaises(frappe.ValidationError, profile.save)  # no branch yet
        profile.reload()  # a refused save leaves the copy in memory out of date
        profile.update({"enabled": 1, "branch_id": "00"})
        profile.save()
        self.assertTrue(frappe.db.get_value("SaaS Tax Profile", other, "enabled"))

    def test_tax_records_are_for_platform_admins_only(self):
        user = "agent-" + frappe.generate_hash(length=6) + "@stemic.test"
        frappe.get_doc({"doctype": "User", "email": user, "first_name": "Agent", "send_welcome_email": 0,
                        "roles": [{"role": "Stemic Agent"}]}).insert(ignore_permissions=True)
        frappe.set_user(user)
        self.assertRaises(frappe.PermissionError, etims.prepare_invoice, **self.args)
        self.assertRaises(frappe.PermissionError, etims.compliance_overview)
        self.assertRaises(frappe.PermissionError, frappe.get_list, "SaaS eTIMS Invoice")

    # ------------------------------------------------------------------ Stemic's own invoices come from SaaS Invoices (#18)
    def stemic_seller(self, treatment="Standard Rated"):
        s = frappe.get_doc("Stemic Tax Settings")
        s.update({"seller_name": "Stemic Schools Ltd", "seller_pin": "P059999999Q", "branch_id": "00", "enabled": 1,
                  "tax_treatment": treatment, "vat_rate": 16})
        s.save()
        frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")

    def saas_invoice(self, months=1):
        from stemic_control import billing

        plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Tax " + frappe.generate_hash(length=5), "enabled": 1,
                               "monthly_price": 11600, "modules": "[]"}).insert().name
        sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": plan, "starts_on": frappe.utils.nowdate()}).insert().name
        return billing.create_invoice(sub, months=months)

    def test_stemic_tax_invoice_is_derived_from_the_saas_invoice(self):
        self.stemic_seller()
        inv = self.saas_invoice()
        out = etims.prepare_from_saas_invoice(inv)
        tax = frappe.get_doc("SaaS eTIMS Invoice", out["name"])
        self.assertEqual((tax.saas_invoice, tax.external_invoice_no, tax.seller_scope), (inv, inv, "Stemic Platform"))
        self.assertEqual((float(tax.net_amount), float(tax.vat_amount), float(tax.total_amount)), (10000, 1600, 11600))
        self.assertEqual(tax.buyer_pin, "P051234567X")  # the school's own KRA PIN, from its tax profile
        self.assertEqual(etims.prepare_from_saas_invoice(inv)["name"], out["name"])  # one tax record per SaaS Invoice

    def test_stemic_invoices_cannot_be_typed_in(self):
        self.stemic_seller()
        inv = self.saas_invoice()
        sub = frappe.db.get_value("SaaS Invoice", inv, "subscription")
        self.assertRaises(frappe.ValidationError, etims.prepare_invoice, **{**self.args, "seller_scope": "Stemic Platform",
                          "subscription": sub, "external_invoice_no": inv, "net_amount": "1", "total_amount": "1"})
        self.assertFalse(hasattr(etims, "prepare_platform_subscription_invoice"))

    def test_only_submitted_saas_invoices_are_prepared(self):
        self.stemic_seller()
        inv = self.saas_invoice()
        frappe.get_doc("SaaS Invoice", inv).cancel()
        self.assertRaises(frappe.ValidationError, etims.prepare_from_saas_invoice, inv)
        self.assertRaises(frappe.ValidationError, etims.prepare_from_saas_invoice, "SINV-NOPE")

    def test_only_kes_saas_invoices_are_prepared(self):
        self.stemic_seller()
        kes = self.saas_invoice()
        self.assertEqual(frappe.db.get_value("SaaS Invoice", kes, "currency"), "KES")
        prepared = etims.prepare_from_saas_invoice(kes)["name"]  # KES invoices still pass

        events = frappe.db.count("SaaS eTIMS Event")
        for currency in ("USD", None):  # the invoice's own currency decides; a blank one is not taken to be KES
            inv = self.saas_invoice()
            frappe.db.set_value("SaaS Invoice", inv, "currency", currency, update_modified=False)
            before = frappe.db.get_value("SaaS Invoice", inv, ["modified", "status", "total"], as_dict=True)
            self.assertEqual(frappe.db.get_single_value("Stemic Settings", "currency") or "KES", "KES")
            self.assertRaises(frappe.ValidationError, etims.prepare_from_saas_invoice, inv)
            self.assertFalse(frappe.db.exists("SaaS eTIMS Invoice", {"saas_invoice": inv}))
            self.assertEqual(frappe.db.get_value("SaaS Invoice", inv, ["modified", "status", "total"], as_dict=True), before)
        self.assertEqual(frappe.db.count("SaaS eTIMS Event"), events)  # refused before any audit record

        # an existing tax invoice is no way around the check: preparing again re-checks the currency
        frappe.db.set_value("SaaS Invoice", kes, "currency", "USD", update_modified=False)
        self.assertRaises(frappe.ValidationError, etims.prepare_from_saas_invoice, kes)
        frappe.db.set_value("SaaS Invoice", kes, "currency", "KES", update_modified=False)
        self.assertEqual(etims.prepare_from_saas_invoice(kes)["name"], prepared)

    def test_cancelling_a_saas_invoice_follows_its_tax_invoice(self):
        self.stemic_seller(treatment="Exempt")
        inv = self.saas_invoice()
        draft = etims.prepare_from_saas_invoice(inv)["name"]
        self.assertEqual(float(frappe.db.get_value("SaaS eTIMS Invoice", draft, "vat_amount")), 0)  # exempt: no VAT
        frappe.get_doc("SaaS Invoice", inv).cancel()  # not yet sent: withdrawn with it
        self.assertEqual(frappe.db.get_value("SaaS eTIMS Invoice", draft, "status"), "Withdrawn")

        sent_inv = self.saas_invoice()
        sent = etims.prepare_from_saas_invoice(sent_inv)["name"]
        frappe.db.set_value("SaaS eTIMS Invoice", sent, "status", "Submitted")
        self.assertRaises(frappe.ValidationError, frappe.get_doc("SaaS Invoice", sent_inv).cancel)  # needs a credit note
        self.assertEqual(frappe.db.get_value("SaaS Invoice", sent_inv, "docstatus"), 1)
