"""Webhook validation and signatures (no external requests)."""
import hashlib
import hmac
import unittest
from unittest.mock import patch

from school_erp.api import webhooks


class TestSchoolWebhooks(unittest.TestCase):
    def test_signature(self):
        self.assertEqual(webhooks.sign('{"x":1}', 'test-secret'),
                         hmac.new(b'test-secret', b'{"x":1}', hashlib.sha256).hexdigest())

    @patch("school_erp.api.webhooks.frappe.throw", side_effect=ValueError)
    def test_reject_http(self, _):
        with self.assertRaises(ValueError):
            webhooks.validate_target("http://example.com/hook")

    @patch("school_erp.api.webhooks.socket.getaddrinfo",
           return_value=[(None, None, None, None, ("127.0.0.1", 443))])
    @patch("school_erp.api.webhooks.frappe.throw", side_effect=ValueError)
    def test_reject_private_target(self, *_):
        with self.assertRaises(ValueError):
            webhooks.validate_target("https://example.org/event")

    @patch("school_erp.api.webhooks.socket.getaddrinfo",
           return_value=[(None, None, None, None, ("8.8.8.8", 443))])
    def test_public_https_target(self, _):
        self.assertEqual(webhooks.validate_target("https://example.org/event"),
                         "https://example.org/event")
