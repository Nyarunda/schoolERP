"""Several platform domains (specs/features/platform-domains): the list in Stemic Settings, choosing one per school,
verification without TXT on Stemic's own domains, routing and going live, the health check, the backfill.
bench --site <site> run-tests --module stemic_control.tests.test_platform_domains"""

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

from stemic_control import api, domains, provisioner, wizard
from stemic_control.tests.helpers import plan, remove_school

ONE, TWO, OLD = "stemic-one.test", "stemic-two.test", "stemic-old.test"


class TestPlatformDomains(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {})
        self._conf.start()
        frappe.local.conf.pop("stemic_platform_domain", None)  # the list decides, not site_config
        self.settings = frappe.get_doc("Stemic Settings")
        self._old_field = self.settings.platform_domain
        self.slugs = []

    def tearDown(self):
        for slug in self.slugs:
            remove_school(slug)
        self.set_domains([], field=self._old_field)
        self._conf.stop()
        frappe.set_user("Administrator")

    def set_domains(self, rows, field=None):
        s = frappe.get_doc("Stemic Settings")
        s.set("platform_domains", [{"domain": d, "enabled": e, "is_default": dflt} for d, e, dflt in rows])
        if field is not None:
            s.platform_domain = field
        s.save(ignore_permissions=True)
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
        frappe.db.commit()

    def two_domains(self, second_enabled=1):
        self.set_domains([(ONE, 1, 1), (TWO, second_enabled, 0)])

    def school(self):
        slug = "pd-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Platform Domain Academy", slug, "head@pd.test")
        self.slugs.append(slug)
        return slug

    # ------------------------------------------------------------------ the list
    def test_no_list_keeps_single_domain(self):
        self.set_domains([], field=OLD)
        self.assertEqual(api.platform_domain(), OLD)
        self.assertEqual(api.offered_domains(), [OLD])

    def test_list_and_default(self):
        self.set_domains([(TWO, 1, 0), (ONE, 1, 1)], field=OLD)
        self.assertEqual(api.platform_domain(), ONE)
        self.assertEqual(api.offered_domains(), [ONE, TWO])  # the default first
        self.assertEqual(frappe.db.get_single_value("Stemic Settings", "platform_domain"), ONE)  # kept in step

    def test_settings_validation(self):
        for rows in ([(ONE, 1, 1), (TWO, 1, 1)],  # two defaults
                     [(ONE, 1, 0), (TWO, 1, 0)],  # none
                     [(ONE, 0, 1)],  # default not offered
                     [("not a domain", 1, 1)],
                     [(ONE, 1, 1), (ONE, 1, 0)]):  # twice
            with self.assertRaises(frappe.ValidationError):
                self.set_domains(rows)

    # ------------------------------------------------------------------ choosing a domain
    def test_slug_check_per_domain(self):
        self.two_domains()
        slug = self.school()
        api.request_domain(slug, f"{slug}.{ONE}")
        self.assertFalse(wizard.check_slug(slug, domain=TWO)["ok"])  # the school name is taken everywhere
        self.assertFalse(wizard.check_slug("admin", domain=TWO)["ok"])
        self.assertFalse(wizard.check_slug("fresh-name-x", domain="elsewhere.test")["ok"])  # not an offered domain
        ok = wizard.check_slug("fresh-name-x", domain=TWO)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["host"], f"fresh-name-x.{TWO}")
        self.assertEqual(wizard.options()["platform_domains"], [ONE, TWO])

    def test_onboard_on_second_domain(self):
        self.two_domains()
        slug = "pd-" + frappe.generate_hash(length=6).lower()
        self.slugs.append(slug)
        r = wizard.onboard_school("Second Domain School", "head@second.test", plan(), start="Internal / Demo", slug=slug,
                                  when="draft", platform_domain=TWO)
        self.assertEqual(r["host"], f"{slug}.{TWO}")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", slug, "platform_domain"), TWO)
        self.assertEqual(frappe.db.get_value("SaaS Domain", f"{slug}.{TWO}", ["domain_type", "status"]),
                         ("Stemic Subdomain", "Verified"))  # no TXT record for Stemic's own domain

    def test_request_domain_any_known(self):
        self.two_domains()
        slug, other = self.school(), self.school()
        self.assertEqual(api.request_domain(slug, f"{slug}.{TWO}")["status"], "Verified")
        with self.assertRaises(frappe.PermissionError):
            api.request_domain(slug, f"{other}.{TWO}")  # another school's name
        with self.assertRaises(frappe.ValidationError):
            api.request_domain(slug, f"www.{TWO}")  # reserved
        custom = api.request_domain(slug, f"portal.{slug}.ac.test")
        self.assertEqual(custom["status"], "Pending Verification")  # schools' own domains still need TXT
        self.assertEqual(frappe.db.get_value("SaaS Tenant", slug, "platform_domain"), ONE)  # registered on the default

    # ------------------------------------------------------------------ routing and going live
    def _bench(self, slug):
        bench = tempfile.mkdtemp(prefix="stemic-pd-")
        site = f"{slug}.{ONE}"  # the site folder is named after the first domain
        os.makedirs(os.path.join(bench, "sites", site, "public", "files"))
        self.addCleanup(shutil.rmtree, bench, True)
        for p in (patch.object(provisioner, "_bench", return_value=bench), patch.object(provisioner, "set_public_url"),
                  patch.dict(frappe.local.conf, {"stemic_domains_file": os.path.join(bench, "routes.json")})):
            p.start()
            self.addCleanup(p.stop)
        return bench, site

    def _serving(self, bench, site):
        def get(url):
            path = os.path.join(bench, "sites", site, "public", "files", url.rsplit("/", 1)[1])
            return SimpleNamespace(status_code=200, text=open(path).read()) if os.path.exists(path) \
                else SimpleNamespace(status_code=404, text="")
        return patch.object(domains, "_get", side_effect=get)

    def test_routed_and_made_primary(self):
        self.two_domains()
        slug = self.school()
        bench, site = self._bench(slug)
        frappe.db.set_value("SaaS Tenant", slug, {"platform_domain": TWO, "status": "Active", "canonical_site": site})
        host = api.request_domain(slug, f"{slug}.{TWO}")["hostname"]
        self.assertEqual(domains.routes().get(host), site)  # sent to the school's site folder
        with patch.object(domains, "_get", return_value=SimpleNamespace(status_code=526, text="")):
            self.assertFalse(domains.try_activate(host))  # not live yet: links stay on the site address
        self.assertEqual(frappe.db.get_value("SaaS Domain", host, "status"), "Verified")
        with self._serving(bench, site), patch("stemic_control.alerts.notify_admins"):
            self.assertTrue(domains.try_activate(host))
        self.assertEqual(frappe.db.get_value("SaaS Domain", host, ["status", "is_primary"]), ("Active", 1))
        self.assertEqual(frappe.db.get_value("SaaS Tenant", slug, "primary_domain"), host)
        self.assertEqual(domains.public_host(slug), host)

    def test_disabled_domain_still_routes(self):
        self.two_domains()
        slug = self.school()
        bench, site = self._bench(slug)
        frappe.db.set_value("SaaS Tenant", slug, {"platform_domain": TWO, "status": "Active", "canonical_site": site})
        host = api.request_domain(slug, f"{slug}.{TWO}")["hostname"]
        self.two_domains(second_enabled=0)
        self.assertNotIn(TWO, api.offered_domains())
        self.assertIn(TWO, api.known_domains())
        self.assertEqual(domains.routes().get(host), site)

    # ------------------------------------------------------------------ health
    def test_health_states(self):
        def probe(code=None, dns=True):
            with patch("socket.getaddrinfo", side_effect=None if dns else OSError("nx")), \
                    patch.object(domains, "_get", return_value=SimpleNamespace(status_code=code, text="")):
                return domains.domain_health(TWO)["state"]
        self.assertEqual(probe(dns=False), "no_dns")
        self.assertEqual(probe(404), "ready")
        self.assertEqual(probe(526), "no_certificate")
        self.assertEqual(probe(522), "no_connection")
        self.assertEqual(probe(418), "unexpected")
        self.two_domains()
        with patch.object(domains, "domain_health", side_effect=lambda d: {"domain": d, "state": "ready", "message": ""}):
            rows = domains.platform_domain_health()
        self.assertEqual([r["domain"] for r in rows][:2], [ONE, TWO])
        self.assertTrue(rows[0]["default"] and rows[0]["offered"])

    # ------------------------------------------------------------------ backfill
    def test_patch_backfills(self):
        from stemic_control.patches import set_school_platform_domains

        self.two_domains()
        on_two, plain = self.school(), self.school()
        api.request_domain(on_two, f"{on_two}.{TWO}")
        frappe.db.set_value("SaaS Tenant", on_two, "platform_domain", None)
        frappe.db.set_value("SaaS Tenant", plain, "platform_domain", None)
        set_school_platform_domains.execute()
        self.assertEqual(frappe.db.get_value("SaaS Tenant", on_two, "platform_domain"), TWO)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", plain, "platform_domain"), ONE)
