"""A school's own domain from verified to live and main address (stemic_control.domains). The server side
(server/stemic-domains-sync) and the internet are faked: the live check's request reads the school's files directly.
bench --site <site> run-tests --module stemic_control.tests.test_domains"""

import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from stemic_control import api, communications, domains, provisioner
from stemic_control.tests.helpers import remove_school

DOMAIN = "stemic.test"


class TestCustomDomains(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.bench = tempfile.mkdtemp(prefix="stemic-domains-")
        self.routes_file = os.path.join(self.bench, "config", "stemic-domains.json")
        self.status_file = os.path.join(self.bench, "domains-status.json")
        self._patches = [
            patch.dict(frappe.local.conf, {"stemic_platform_domain": DOMAIN, "stemic_domains_file": self.routes_file,
                                           "stemic_domains_status_file": self.status_file}),
            patch.object(provisioner, "_bench", return_value=self.bench),
            patch.object(provisioner, "set_public_url"),
        ]
        for p in self._patches:
            p.start()
        self.set_public_url = provisioner.set_public_url
        self.slug = "dom-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Domain Academy", self.slug, "head@domain.test")
        self.site = f"{self.slug}.localhost"
        frappe.db.set_value("SaaS Tenant", self.slug, {"status": "Active", "canonical_site": self.site,
                                                       "primary_domain": f"{self.slug}.{DOMAIN}"})
        os.makedirs(os.path.join(self.bench, "sites", self.site, "public", "files"))
        self.host = f"portal.{self.slug}.ac.test"

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        remove_school(self.slug)  # hourly() commits
        shutil.rmtree(self.bench, ignore_errors=True)
        frappe.set_user("Administrator")

    def claim(self, verify=True):
        data = api.request_domain(self.slug, self.host)
        if verify:
            with patch.object(api, "_txt_records", return_value=[data["verification_value"]]):
                api.verify_domain(data["domain"])
        return data["domain"]

    def published(self):
        with open(self.routes_file) as f:
            return json.load(f)["domains"]

    def serving(self, site=None):
        """The internet, faked: https://<host>/files/<name> answers with that site's file."""
        def get(url):
            name = url.rsplit("/", 1)[1]
            path = os.path.join(self.bench, "sites", site or self.site, "public", "files", name)
            if os.path.exists(path):
                return SimpleNamespace(status_code=200, text=open(path).read())
            return SimpleNamespace(status_code=404, text="Not Found")
        return patch.object(domains, "_get", side_effect=get)

    def answering(self, code):
        return patch.object(domains, "_get", return_value=SimpleNamespace(status_code=code, text=""))

    def test_verifying_routes_the_domain_to_the_school(self):
        domain = self.claim(verify=False)
        self.assertNotIn(self.host, domains.routes())  # not before DNS proves ownership
        with patch.object(api, "_txt_records", return_value=[frappe.db.get_value("SaaS Domain", domain, "verification_token")]):
            api.verify_domain(domain)
        self.assertEqual(self.published().get(self.host), self.site)

    def test_a_school_without_a_site_is_routed_once_its_site_exists(self):
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", None)
        self.claim()
        self.assertNotIn(self.host, self.published())
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", self.site)
        self.assertEqual(domains.publish().get(self.host), self.site)

    def test_live_only_when_the_domain_returns_this_schools_file(self):
        domain = self.claim()
        with self.serving():
            self.assertEqual(domains.activate(domain)["status"], "Active")
        self.assertEqual(os.listdir(os.path.join(self.bench, "sites", self.site, "public", "files")), [])  # cleaned up

    def test_another_site_answering_is_not_live(self):
        domain = self.claim()
        other = "other.localhost"
        os.makedirs(os.path.join(self.bench, "sites", other, "public", "files"))
        with self.serving(other), self.assertRaises(frappe.ValidationError):
            domains.activate(domain)
        self.assertEqual(frappe.db.get_value("SaaS Domain", domain, "status"), "Verified")

    def test_says_what_to_fix(self):
        domain = self.claim()
        with self.answering(526):
            self.assertIn("No certificate on the server covers", domains.check(domain)["problem"])
        with self.answering(404):
            self.assertIn("install stemic-domains-sync", domains.check(domain)["problem"])
        with open(self.status_file, "w") as f:
            json.dump({"domains": {self.host: {"problem": "nginx_failed"}}}, f)
        with self.answering(404):
            self.assertIn("nginx rejected", domains.check(domain)["problem"])
        with patch.object(domains, "_get", side_effect=OSError("no route")), \
                patch("socket.getaddrinfo", side_effect=OSError("NXDOMAIN")):
            self.assertIn(f"CNAME {self.host} -> {DOMAIN}", domains.check(domain)["problem"])

    def test_pending_or_subdomain_cannot_be_activated(self):
        pending = self.claim(verify=False)
        self.assertRaises(frappe.ValidationError, domains.activate, pending)
        sub = api.request_domain(self.slug, f"{self.slug}.{DOMAIN}")["domain"]
        self.assertRaises(frappe.ValidationError, domains.activate, sub)

    def test_primary_moves_the_schools_links_and_disable_moves_them_back(self):
        domain = self.claim()
        self.assertRaises(frappe.ValidationError, domains.make_primary, domain)  # not live yet
        with self.serving():
            domains.activate(domain)
        self.assertEqual(domains.public_host(self.slug), self.site)  # live, but not the main address yet
        domains.make_primary(domain)
        self.set_public_url.assert_called_with(self.site, self.host)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "primary_domain"), self.host)
        self.assertEqual(domains.public_host(self.slug), self.host)
        lic = frappe._dict(tenant=self.slug, school_name="Domain Academy", site=self.site, plan="P", modules="",
                           expires_on=None, signed_key="KEY")
        self.assertIn(f"https://{self.host}", communications.render_license(lic)[1])

        domains.disable(domain)
        self.set_public_url.assert_called_with(self.site, self.site)
        self.assertEqual(frappe.db.get_value("SaaS Domain", domain, ["status", "is_primary"]), ("Disabled", 0))
        self.assertEqual(domains.public_host(self.slug), self.site)
        self.assertNotIn(self.host, self.published())

    def test_hourly_activates_what_has_gone_live(self):
        domain = self.claim()
        with self.answering(526):
            domains.hourly()
        self.assertEqual(frappe.db.get_value("SaaS Domain", domain, "status"), "Verified")
        with self.serving(), patch("stemic_control.alerts.notify_admins") as notify:
            domains.hourly()
        self.assertEqual(frappe.db.get_value("SaaS Domain", domain, "status"), "Active")
        notify.assert_called_once()

    def test_only_platform_admins(self):
        domain = self.claim()
        frappe.set_user("Guest")
        for action in (domains.activate, domains.make_primary, domains.disable, domains.status):
            self.assertRaises(frappe.PermissionError, action, domain)
