"""Plans, subscription billing states and signed license keys, against a database.
bench --site <site> run-tests --module stemic_control.tests.test_billing"""

import json
import os
import tempfile
from datetime import date
from unittest.mock import patch

import frappe
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, licensing, policy


class TestBilling(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        priv = Ed25519PrivateKey.generate()
        raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        self.public = licensing._b64e(priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        fd, self.key_file = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            f.write(licensing._b64e(raw))
        self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test",
                                                    "stemic_license_private_key_file": self.key_file})
        self._conf.start()
        slug = "bill-" + frappe.generate_hash(length=6).lower()
        self.tenant = api.register_tenant("Billing Academy", slug, "head@bill.test")
        frappe.db.set_value("SaaS Tenant", self.tenant, "canonical_site", f"{slug}.localhost")
        self.plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Bill " + frappe.generate_hash(length=5), "enabled": 1,
                                    "monthly_price": 5000, "student_limit": 400,
                                    "modules": json.dumps(["portal", "fees"])}).insert().name
        self.sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": self.plan,
                                   "starts_on": frappe.utils.nowdate(),
                                   "ends_on": frappe.utils.add_months(frappe.utils.nowdate(), 12)}).insert().name

    def tearDown(self):
        self._conf.stop()
        os.remove(self.key_file)

    def test_plan_modules_are_checked_and_ordered(self):
        self.assertEqual(json.loads(frappe.db.get_value("SaaS Plan", self.plan, "modules")), ["fees", "portal"])
        doc = frappe.get_doc("SaaS Plan", self.plan)
        doc.modules = json.dumps(["fees", "teleport"])
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_status_moves_follow_the_rules(self):
        self.assertRaises(frappe.ValidationError, api.set_subscription_status, self.sub, "Active")  # no payment ref
        api.set_subscription_status(self.sub, "Active", "QX12AB")
        self.assertRaises(frappe.ValidationError, api.set_subscription_status, self.sub, "Grace")  # Active -> Grace skips Past Due
        api.set_subscription_status(self.sub, "Cancelled")
        self.assertRaises(frappe.ValidationError, api.renew_subscription, self.sub, 12, "QX99")

    def test_renew_extends_from_the_end_date(self):
        end = frappe.db.get_value("SaaS Subscription", self.sub, "ends_on")
        api.set_subscription_status(self.sub, "Past Due")
        out = api.renew_subscription(self.sub, 3, "RENEW1")
        self.assertEqual(out["ends_on"], str(frappe.utils.add_months(end, 3)))
        self.assertEqual(frappe.db.get_value("SaaS Subscription", self.sub, "status"), "Active")

    def test_issued_key_is_accepted_by_school_erp(self):
        name = api.issue_license(self.sub)["license"]
        lic = frappe.get_doc("SaaS License", name)
        self.assertEqual(lic.status, "Issued")
        payload = licensing.decode(lic.signed_key)
        self.assertEqual(payload["modules"], ["fees", "portal"])
        self.assertEqual(payload["max_students"], 400)
        self.assertEqual(payload["site"], lic.site)
        try:
            from school_erp.logic import license as school_license
        except ImportError:
            return
        state = school_license.evaluate(lic.signed_key, self.public, date.today(), site=lic.site)
        self.assertEqual(state["status"], "valid")
        self.assertEqual(state["modules"], ["core", "fees", "portal"])
        self.assertEqual(state["max_students"], 400)
        self.assertEqual(set(policy.MODULES), set(school_license.MODULES))  # the two module lists must not drift

    def test_new_key_revokes_the_old_one(self):
        first = api.issue_license(self.sub)["license"]
        second = api.issue_license(self.sub)["license"]
        self.assertEqual(frappe.db.get_value("SaaS License", first, "status"), "Revoked")
        self.assertEqual(frappe.db.get_value("SaaS License", second, "status"), "Issued")
        api.revoke_license(second)
        self.assertRaises(frappe.ValidationError, api.revoke_license, second)

    def test_no_key_without_a_site_or_while_suspended(self):
        frappe.db.set_value("SaaS Tenant", self.tenant, "canonical_site", None)
        self.assertRaises(frappe.ValidationError, api.issue_license, self.sub)
        frappe.db.set_value("SaaS Tenant", self.tenant, "canonical_site", "x.localhost")
        api.set_subscription_status(self.sub, "Past Due")
        api.set_subscription_status(self.sub, "Suspended")
        self.assertRaises(frappe.ValidationError, api.issue_license, self.sub)

    def test_licenses_cannot_be_made_by_hand(self):
        doc = frappe.get_doc({"doctype": "SaaS License", "tenant": self.tenant, "subscription": self.sub})
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_no_signing_without_the_private_key(self):
        with patch.dict(frappe.local.conf, {"stemic_license_private_key_file": None}):
            self.assertRaises(frappe.ValidationError, api.issue_license, self.sub)
