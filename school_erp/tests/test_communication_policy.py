"""SMS limits: keep unlimited default and scope caps to local school day/month."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from school_erp.api.communication_policy import period_limits


class TestCommunicationPolicy(unittest.TestCase):
    def test_unlimited_defaults(self):
        settings = {"sms_daily_limit": 0, "sms_monthly_limit": 0}
        self.assertEqual(period_limits(settings, "2026-10-28"),
                         (("D:2026-10-28", "Day", 0), ("M:2026-10", "Month", 0)))

    def test_daily_and_monthly_periods(self):
        settings = {"sms_daily_limit": 100, "sms_monthly_limit": 2000}
        self.assertEqual(period_limits(settings, "2026-10-28"),
                         (("D:2026-10-28", "Day", 100), ("M:2026-10", "Month", 2000)))

    def test_negative_limits_are_unlimited(self):
        settings = {"sms_daily_limit": -5, "sms_monthly_limit": -2}
        self.assertEqual([x[2] for x in period_limits(settings, "2026-10-28")], [0, 0])
