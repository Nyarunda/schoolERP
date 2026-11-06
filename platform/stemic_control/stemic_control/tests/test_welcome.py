"""The welcome email a school's contact gets when its site is built: address, username and a set-password link, never a
password. The school's site and email sending are faked (nothing is built or sent).
bench --site <site> run-tests --module stemic_control.tests.test_welcome"""

from unittest.mock import patch

import frappe
from frappe.utils import get_bench_path

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, provisioner, welcome
from stemic_control.tests.helpers import make_eligible, remove_school

CONF = {"stemic_platform_domain": "stemic.test", "stemic_local_provisioner": 1, "stemic_db_root_password": "root-secret-123",
        "stemic_site_domain": "localhost", "stemic_provision_environment": "development",
        "stemic_provision_allowed_benches": [get_bench_path()]}
LISTED = "frappe     16.0.0 version-16\nerpnext    16.0.0 version-16\nschool_erp 1.0.0   main\n"
LINK = "https://wel.example/update-password?key=ONE-TIME-KEY"


class TestWelcome(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._patches = [patch.object(provisioner, "enqueue"), patch.object(provisioner, "_database_exists", return_value=False),
                         patch.object(provisioner, "_site_dir_exists", return_value=False)]
        for p in self._patches:
            p.start()
        self._mail = patch.object(frappe, "sendmail")
        self.sendmail = self._mail.start()
        self.slug = "wel-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Welcome Academy", self.slug, "Head@Welcome.Test")
        make_eligible(self.slug)
        self.job = api.queue_provisioning(self.slug, "wel-" + frappe.generate_hash(length=12))
        self.calls = []

    def tearDown(self):
        self._mail.stop()
        for p in self._patches:
            p.stop()
        self._conf.stop()
        frappe.set_user("Administrator")
        remove_school(self.slug)

    def cli(self, school_reply=None):
        def fake(*args, **kwargs):
            self.calls.append(args)
            if "execute" in args:
                return school_reply if school_reply is not None else f'noise\n{{"user": "head@welcome.test", "link": "{LINK}", "hours": 24}}\n'
            return LISTED if "list-apps" in args else ""
        return patch.object(provisioner, "_frappe_cli", side_effect=fake)

    def test_a_built_school_is_emailed_its_address_and_a_set_password_link(self):
        with self.cli():
            self.assertEqual(provisioner.run(self.job), "Succeeded")
        site = f"{self.slug}.localhost"
        execute = next(c for c in self.calls if "execute" in c)
        self.assertEqual(execute[:4], ("--site", site, "execute", "school_erp.setup.first_admin.create"))
        self.assertIn("Head@Welcome.Test", execute[-1])
        mail = self.sendmail.call_args.kwargs
        self.assertEqual((mail["recipients"], mail["reference_name"]), (["Head@Welcome.Test"], self.slug))
        self.assertIn("Welcome Academy is ready", mail["subject"])
        self.assertIn(LINK, mail["message"])
        self.assertIn(f"https://{site}", mail["message"])
        self.assertIn("head@welcome.test", mail["message"])
        self.assertNotIn("root-secret-123", mail["message"])
        self.assertNotIn(api.site_access(self.slug)["password"], mail["message"])  # never the Administrator password
        self.assertTrue(frappe.db.get_value("SaaS Tenant", self.slug, "welcome_sent_on"))

    def test_a_failed_welcome_never_undoes_the_build_and_the_admins_are_told(self):
        with self.cli(school_reply="Traceback: something broke\n"), \
                patch("stemic_control.alerts.notify_admins") as alert:
            self.assertEqual(provisioner.run(self.job), "Succeeded")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Active")
        self.sendmail.assert_not_called()
        self.assertFalse(frappe.db.get_value("SaaS Tenant", self.slug, "welcome_sent_on"))
        # (the automatic licence may alert too: there is no signing key in tests)
        self.assertTrue(any("welcome email" in c.args[0] for c in alert.call_args_list))
        self.assertTrue(frappe.db.exists("Error Log", {"method": f"Welcome email not sent for {self.slug}"}))

    def test_resend_gives_a_fresh_link_and_is_for_platform_admins_only(self):
        with self.cli():
            provisioner.run(self.job)
            self.sendmail.reset_mock()
            self.assertEqual(welcome.resend(self.slug)["to"], "Head@Welcome.Test")
        self.assertEqual(self.sendmail.call_count, 1)
        self.assertEqual(sum("execute" in c for c in self.calls), 2)  # a new link from the school's site each time
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, welcome.resend, self.slug)

    def test_no_welcome_before_the_site_is_ready(self):
        self.assertRaises(frappe.ValidationError, welcome.send, self.slug)
        self.sendmail.assert_not_called()

    def test_the_welcome_carries_the_payment_details(self):
        from stemic_control import billing

        sub = frappe.db.get_value("SaaS Subscription", {"tenant": self.slug}, ["name", "plan"], as_dict=True)
        frappe.db.set_value("SaaS Plan", sub.plan, "monthly_price", 9500)
        inv = billing.create_invoice(sub.name, months=12)
        with self.cli(), patch.dict(frappe.local.conf, {}), \
                patch("stemic_control.communications._instructions", side_effect=lambda i: f"Paybill 123456, Account {i}"):
            provisioner.run(self.job)
        message = self.sendmail.call_args.kwargs["message"]
        self.assertIn(sub.plan, message)
        self.assertIn("9,500", message)  # the plan's monthly price
        self.assertIn(inv, message)  # the latest invoice, still owed
        self.assertIn(f"Paybill 123456, Account {inv}", message)  # how to pay that invoice
        self.assertIn("Set your password", message)
