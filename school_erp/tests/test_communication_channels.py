"""School-wide channel switches must block delivery at the last sending boundary."""

import unittest
from unittest.mock import MagicMock, patch

from school_erp.api import messaging


class TestCommunicationChannelControls(unittest.TestCase):
    @patch("school_erp.api.messaging.licensing.require")
    @patch("school_erp.api.messaging.frappe.get_cached_doc")
    @patch("school_erp.api.messaging._send_frappe")
    def test_disabled_sms_never_calls_provider(self, provider, get_settings, require):
        get_settings.return_value = {"enable_sms_notifications": 0}
        result = messaging.send_sms(["0712345678"], "Hello")
        self.assertTrue(result["skipped"])
        self.assertEqual(result["sent"], [])
        self.assertEqual(result["failed"], [])
        provider.assert_not_called()

    @patch("school_erp.api.messaging.licensing.require")
    @patch("school_erp.api.messaging.frappe.get_cached_doc")
    @patch("school_erp.api.messaging._send_frappe")
    @patch("school_erp.api.messaging.normalize_phone", return_value="254712345678")
    def test_enabled_sms_preserves_existing_provider(self, normalize, provider, get_settings, require):
        get_settings.return_value = MagicMock(sms_provider="Frappe SMS Settings", country_code="254")
        get_settings.return_value.get.return_value = 1
        provider.return_value = {"sent": ["254712345678"], "failed": []}
        result = messaging.send_sms(["0712345678"], "Hello")
        self.assertEqual(result["sent"], ["254712345678"])
        provider.assert_called_once_with(["254712345678"], "Hello")

    @patch("school_erp.api.messaging.frappe.get_cached_doc")
    @patch("school_erp.api.messaging._guardians")
    @patch("school_erp.api.messaging.frappe.sendmail")
    def test_disabled_email_never_queues_message(self, sendmail, guardians, get_settings):
        get_settings.return_value = {"enable_email_notifications": 0}
        result = messaging.email_student(MagicMock(), "Subject", "Body", attach_statement=False)
        self.assertEqual(result, 0)
        guardians.assert_not_called()
        sendmail.assert_not_called()

    @patch("school_erp.api.messaging.frappe.get_cached_doc")
    @patch("school_erp.api.messaging._guardians")
    @patch("school_erp.api.messaging.message_context", return_value={})
    @patch("school_erp.api.messaging.frappe.sendmail")
    def test_enabled_email_uses_frappe_queue(self, sendmail, context, guardians, get_settings):
        get_settings.return_value = {"enable_email_notifications": 1}
        guardians.return_value = [{"email": "parent@example.test"}]
        student = MagicMock(name="STU-0001")
        student.name = "STU-0001"
        result = messaging.email_student(student, "Subject", "Body", attach_statement=False)
        self.assertEqual(result, 1)
        sendmail.assert_called_once()
        self.assertFalse(sendmail.call_args.kwargs["now"])


if __name__ == "__main__":
    unittest.main()
