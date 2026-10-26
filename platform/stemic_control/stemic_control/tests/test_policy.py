"""Framework-free checks of control-plane rules: run with  pytest stemic_control/tests/test_policy.py"""

import unittest

from stemic_control import policy


class TestPolicy(unittest.TestCase):
    def test_hostnames(self):
        for good in ("greenfield.stemischools.com", "portal.greenfield.ac.ke", "school.com", "a-b.co.ke"):
            self.assertTrue(policy.is_hostname(good), good)
        for bad in ("http://evil.com", "127.0.0.1", "a/../b.com", "foo..com", "x\\.com", "-a.com", "com", "a.c", "", "a b.com"):
            self.assertFalse(policy.is_hostname(bad), bad)

    def test_platform_hosts(self):
        self.assertTrue(policy.subdomain_of("greenfield.stemic.cloud", "stemic.cloud"))
        self.assertFalse(policy.subdomain_of("evilstemic.cloud", "stemic.cloud"))
        self.assertIn("admin.stemic.cloud", policy.reserved_hosts("stemic.cloud"))
        self.assertIn("stemic.cloud", policy.reserved_hosts("stemic.cloud"))

    def test_transitions(self):
        t = policy.TENANT_TRANSITIONS
        self.assertTrue(policy.can_move(t, "Draft", "Pending"))
        self.assertTrue(policy.can_move(t, "Active", "Active"))
        self.assertFalse(policy.can_move(t, "Draft", "Active"))  # only a finished job activates a school
        self.assertFalse(policy.can_move(t, "Suspended", "Draft"))
        self.assertFalse(policy.can_move(policy.JOB_TRANSITIONS, "Succeeded", "Running"))
        self.assertEqual(policy.JOB_EFFECT[("Create Site", "Succeeded")], "Active")

    def test_txt_values(self):
        answer = {"Answer": [
            {"name": "_stemic-verification.x.com.", "type": 16, "data": '"abc"'},
            {"name": "_stemic-verification.x.com.", "type": 16, "data": '"part1" "part2"'},
            {"name": "x.com.", "type": 5, "data": "other.com."},
        ]}
        self.assertEqual(policy.txt_values(answer), ["abc", "part1part2"])
        self.assertEqual(policy.txt_values({"Status": 3}), [])
