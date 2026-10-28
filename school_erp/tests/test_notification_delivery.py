"""Notification ledger contracts; no live provider credentials required."""
import unittest
from unittest.mock import MagicMock, patch

from school_erp.api import notification_delivery as delivery


class TestNotificationDelivery(unittest.TestCase):
    def test_key_is_deterministic(self):
        self.assertEqual(
            delivery.delivery_key("payment-123", "SMS", "254700000000"),
            delivery.delivery_key("payment-123", "SMS", "254700000000"),
        )

    def test_key_is_per_channel_and_recipient(self):
        key = delivery.delivery_key("payment-123", "SMS", "254700000000")
        self.assertNotEqual(key, delivery.delivery_key("payment-123", "Email", "254700000000"))
        self.assertNotEqual(key, delivery.delivery_key("payment-123", "SMS", "254711111111"))

    @patch("school_erp.api.notification_delivery.frappe.db.get_value")
    @patch("school_erp.api.notification_delivery.frappe.enqueue")
    def test_duplicate_existing_is_not_enqueued(self, enqueue, get_value):
        get_value.return_value = "delivery-1"
        self.assertEqual(
            delivery.queue_delivery("payment-123", "SMS", "254700000000", "Paid"),
            "delivery-1",
        )
        enqueue.assert_not_called()

    @patch("school_erp.api.notification_delivery.frappe.db.sql")
    def test_non_queued_is_not_dispatched(self, sql):
        sql.return_value = [MagicMock(status="Accepted", attempts=1)]
        with patch("school_erp.api.notification_delivery.frappe.get_doc") as get_doc:
            delivery.process_delivery("del-1")
            get_doc.assert_not_called()

    @patch("school_erp.api.notification_delivery.frappe.enqueue")
    @patch("school_erp.api.notification_delivery.frappe.get_all")
    def test_retry_scan_only_queues_due_records(self, get_all, enqueue):
        get_all.return_value = ["del-1"]
        delivery.retry_due()
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(enqueue.call_args.kwargs["name"], "del-1")
        self.assertEqual(get_all.call_args.kwargs["filters"]["status"], "Retrying")
