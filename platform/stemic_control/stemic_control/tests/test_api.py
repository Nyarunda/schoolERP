"""Tenant identifier rules as the API exposes them."""

import unittest

from stemic_control.api import HOST, RESERVED, SLUG


class TestTenantIdentifiers(unittest.TestCase):
    def test_valid_slug(self):
        self.assertTrue(SLUG.fullmatch("greenfield-academy"))
        self.assertFalse(SLUG.fullmatch("../school"))
        self.assertTrue(SLUG.fullmatch("root"))
        self.assertIn("admin", RESERVED)

    def test_hostname(self):
        self.assertTrue(HOST.fullmatch("greenfield.stemicschools.com"))
        self.assertTrue(HOST.fullmatch("portal.greenfield.ac.ke"))
        for value in ["http://evil.com", "127.0.0.1", "a/../b.com", "foo..com", "x\\.com"]:
            self.assertFalse(HOST.fullmatch(value))
