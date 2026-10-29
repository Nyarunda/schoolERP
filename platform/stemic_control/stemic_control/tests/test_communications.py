"""What Stemic tells schools, by email and SMS: invoices, receipts, overdue reminders, license keys, suspension, and the
welcome SMS. Email sending and the SMS gateway's HTTP are faked (nothing leaves the machine).
bench --site <site> run-tests --module stemic_control.tests.test_communications"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, billing, communications

PHONE = "0712 345 678"
SMS_KEY = "sms-secret-key-123"


class TestCommunications(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {"stemic_platform_domain": "stemic.test"})
        self._conf.start()
        self.settings({"notify_schools_by_email": 1, "notify_schools_by_sms": 0, "payment_instructions": "Paybill 999999, Account {invoice}",
                       **{f: 1 for f in set(communications.EVENTS.values())}})
        self._mail = patch.object(frappe, "sendmail")
        self.sendmail = self._mail.start()
        self._enqueue = patch.object(frappe, "enqueue")
        self.enqueue = self._enqueue.start()
        self._sms = patch("school_erp.api.sms_gateway._request", return_value=(200, '{"status": "Success"}'))
        self.http = self._sms.start()
        slug = "com-" + frappe.generate_hash(length=6).lower()
        self.tenant = api.register_tenant("Comms Academy", slug, "head@comms.test", contact_phone=PHONE)
        self.plan = frappe.get_doc({"doctype": "SaaS Plan", "plan_name": "Comms " + frappe.generate_hash(length=5), "enabled": 1,
                                    "monthly_price": 5000, "modules": "[]"}).insert().name
        self.sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": self.tenant, "plan": self.plan,
                                   "starts_on": nowdate(), "ends_on": add_days(nowdate(), 10)}).insert().name

    def tearDown(self):
        self._sms.stop()
        self._enqueue.stop()
        self._mail.stop()
        self._conf.stop()
        frappe.set_user("Administrator")
        frappe.db.rollback()
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

    def settings(self, values):
        frappe.db.set_single_value("Stemic Settings", values)
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

    def sms_on(self, **extra):
        self.settings({"notify_schools_by_sms": 1, "sms_url": "https://sms.example.test/send", "sms_http_method": "POST",
                       "sms_body_format": "JSON", "sms_recipient_param": "mobile", "sms_message_param": "message",
                       "sms_api_key_param": "apikey", "sms_success_field": "status", "sms_success_values": "Success",
                       "sms_parameters": "partnerID=42\nheader:X-Client=stemic", **extra})
        s = frappe.get_doc("Stemic Settings")
        s.sms_api_key = SMS_KEY
        with patch("school_erp.api.sms_gateway._lookup", return_value=["93.184.216.34"]):
            s.save()
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")

    def run_queued(self, event):
        """Run what was queued for `event` (the background job), as the worker would after commit."""
        calls = [c.kwargs for c in self.enqueue.call_args_list if c.args and c.args[0] == "stemic_control.communications.send_event"
                 and c.kwargs.get("event") == event]
        self.assertTrue(calls, f"{event} was not queued")
        self.assertTrue(all(c["enqueue_after_commit"] for c in calls))  # never announced before it is committed
        kwargs = {k: v for k, v in calls[-1].items() if k not in ("queue", "enqueue_after_commit")}
        return communications.send_event(**kwargs)

    def logs(self, event):
        return frappe.get_all("SaaS Communication", filters={"tenant": self.tenant, "event": event},
                              fields=["channel", "status", "recipient", "detail"], order_by="channel")

    def pay(self, invoice, amount):
        return billing.record_payment(invoice, amount, "M-Pesa", "Q" + frappe.generate_hash(length=8).upper())

    # ------------------------------------------------------------------ email
    def test_invoice_email_has_the_amount_due_date_and_how_to_pay(self):
        inv = billing.create_invoice(self.sub, months=3)
        self.run_queued("Invoice Issued")
        mail = self.sendmail.call_args.kwargs
        self.assertEqual(mail["recipients"], ["head@comms.test"])
        self.assertIn(inv, mail["subject"])
        self.assertIn("15,000", mail["message"])
        self.assertIn(f"Paybill 999999, Account {inv}", mail["message"])
        self.assertEqual([(l.channel, l.status) for l in self.logs("Invoice Issued")], [("Email", "Sent")])

    def test_the_same_invoice_is_never_announced_twice(self):
        billing.create_invoice(self.sub, months=1)
        self.run_queued("Invoice Issued")
        self.run_queued("Invoice Issued")  # a retried job
        self.assertEqual(self.sendmail.call_count, 1)

    def test_receipt_shows_the_balance_and_paid_until(self):
        inv = billing.create_invoice(self.sub, months=2)
        self.pay(inv, 4000)
        self.run_queued("Payment Received")
        mail = self.sendmail.call_args.kwargs
        self.assertIn("4,000", mail["message"])
        self.assertIn("6,000", mail["message"])  # still owed

    def test_overdue_reminder_is_sent_once(self):
        inv = frappe.get_doc("SaaS Invoice", billing.create_invoice(self.sub, months=1))
        frappe.db.set_value("SaaS Invoice", inv.name, "due_date", add_days(nowdate(), -3))
        with patch.object(frappe.db, "commit"):
            billing.daily()
        self.run_queued("Invoice Overdue")
        self.run_queued("Invoice Overdue")
        self.assertEqual(sum("Overdue" in c.kwargs["subject"] for c in self.sendmail.call_args_list), 1)

    def test_suspension_and_resumption_are_each_announced(self):
        frappe.db.set_value("SaaS Tenant", self.tenant, "status", "Active")
        api.set_tenant_status(self.tenant, "Suspended")
        self.run_queued("Suspended")
        api.set_tenant_status(self.tenant, "Active")
        self.run_queued("Resumed")
        subjects = [c.kwargs["subject"] for c in self.sendmail.call_args_list]
        self.assertTrue(any("suspended" in s for s in subjects) and any("active again" in s for s in subjects))

    def test_switched_off_events_are_not_sent(self):
        self.settings({"notify_invoice": 0})
        billing.create_invoice(self.sub, months=1)
        self.assertFalse([c for c in self.enqueue.call_args_list if c.kwargs.get("event") == "Invoice Issued"])

    # ------------------------------------------------------------------ SMS
    def test_sms_goes_out_when_switched_on_through_the_platform_gateway(self):
        self.sms_on()
        inv = billing.create_invoice(self.sub, months=1)
        self.run_queued("Invoice Issued")
        gw, _url, method, fields, headers = self.http.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(fields["mobile"], "254712345678")
        self.assertIn(inv, fields["message"])
        self.assertIn("Paybill 999999", fields["message"])
        self.assertEqual((fields["apikey"], fields["partnerID"], headers["X-Client"]), (SMS_KEY, "42", "stemic"))
        self.assertEqual([(l.channel, l.status) for l in self.logs("Invoice Issued")], [("Email", "Sent"), ("SMS", "Sent")])

    def test_no_sms_when_off_or_without_a_phone(self):
        billing.create_invoice(self.sub, months=1)
        self.run_queued("Invoice Issued")
        self.http.assert_not_called()  # SMS off: email only, nothing logged for SMS
        self.assertEqual([l.channel for l in self.logs("Invoice Issued")], ["Email"])
        self.sms_on()
        frappe.db.set_value("SaaS Tenant", self.tenant, "contact_phone", None)
        communications.deliver(self.tenant, "Suspended", ("SaaS Tenant", self.tenant), sms="x", dedupe=False)
        self.assertEqual([(l.status, l.detail) for l in self.logs("Suspended")], [("Skipped", "The school has no contact phone")])

    def test_a_refused_sms_is_failed_with_the_reason_and_the_email_still_goes(self):
        self.sms_on()
        self.http.return_value = (200, '{"status": "InsufficientBalance"}')
        billing.create_invoice(self.sub, months=1)
        self.run_queued("Invoice Issued")
        sms = [l for l in self.logs("Invoice Issued") if l.channel == "SMS"][0]
        self.assertEqual(sms.status, "Failed")
        self.assertIn("InsufficientBalance", sms.detail)
        self.assertNotIn(SMS_KEY, sms.detail)
        self.assertEqual(self.sendmail.call_count, 1)

    def test_license_key_goes_by_email_only(self):
        self.sms_on()
        frappe.db.set_value("SaaS Tenant", self.tenant, "canonical_site", "comms.localhost")
        lic = frappe.get_doc({"doctype": "SaaS License", "tenant": self.tenant, "subscription": self.sub, "plan": self.plan,
                              "site": "comms.localhost", "issued_on": nowdate(), "modules": "Fees"})
        lic.signed_key, lic.status = "SIGNED-LICENSE-KEY-ABC", "Issued"
        lic.flags.from_issue = True
        lic.insert()
        communications.send_event("License Issued", license=lic.name)
        self.assertIn("SIGNED-LICENSE-KEY-ABC", self.sendmail.call_args.kwargs["message"])
        sms_text = self.http.call_args.args[3]["message"]
        self.assertNotIn("SIGNED-LICENSE-KEY-ABC", sms_text)
        self.assertIn("in your email", sms_text)

    def test_the_gateway_url_must_be_public_https(self):
        with self.assertRaises(frappe.ValidationError):
            self.sms_on(sms_url="http://sms.example.test/send")

    def test_welcome_sms_points_to_the_email_and_carries_no_link(self):
        from stemic_control import provisioner, welcome

        self.sms_on()
        frappe.db.set_value("SaaS Tenant", self.tenant, {"status": "Active", "canonical_site": "comms.localhost"})
        reply = '{"user": "head@comms.test", "link": "http://comms.localhost/update-password?key=SECRET-LINK", "hours": 24}'
        with patch.object(provisioner, "_frappe_cli", return_value=reply):
            welcome.send(self.tenant)
        sms_text = self.http.call_args.args[3]["message"]
        self.assertIn("https://comms.localhost", sms_text)
        self.assertIn("head@comms.test", sms_text)
        self.assertNotIn("SECRET-LINK", sms_text)
        self.assertEqual([(l.channel, l.status) for l in self.logs("Welcome")], [("Email", "Sent"), ("SMS", "Sent")])
