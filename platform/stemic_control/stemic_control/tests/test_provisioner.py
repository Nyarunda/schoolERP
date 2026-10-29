"""Local provisioner against a database, with Frappe's CLI mocked (no real sites are created).
bench --site <site> run-tests --module stemic_control.tests.test_provisioner"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase as TestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as TestCase

from frappe.utils import get_bench_path

from stemic_control import api, provisioner
from stemic_control.tests.helpers import make_eligible, remove_school

CONF = {"stemic_platform_domain": "stemic.test", "stemic_local_provisioner": 1, "stemic_db_root_password": "root-secret-123",
        "stemic_site_domain": "localhost", "stemic_provision_environment": "development",
        "stemic_provision_allowed_benches": [get_bench_path()]}
LISTED = "frappe     16.0.0 version-16\nerpnext    16.0.0 version-16\nschool_erp 1.0.0   main\n"


class TestProvisioner(TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, CONF)
        self._conf.start()
        self._enqueue = patch.object(provisioner, "enqueue")  # tests call run() directly
        self._enqueue.start()
        self._db = patch.object(provisioner, "_database_exists", return_value=False)  # no real MariaDB root login
        self._db.start()
        self.slug = "prov-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Provisioned School", self.slug, "head@prov.test")
        make_eligible(self.slug)
        api.request_domain(self.slug, f"{self.slug}.stemic.test")
        self.job = api.queue_provisioning(self.slug, "prov-" + frappe.generate_hash(length=12))

    def tearDown(self):
        self._db.stop()
        self._enqueue.stop()
        self._conf.stop()
        # provisioner.run commits, so this school would outlive the test; left Queued, a real scheduler on the same
        # site (with the local provisioner on) would later build an actual prov-* site for it
        remove_school(self.slug)

    def cli(self, fail_new_site=False):
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            if args[0] == "new-site" and fail_new_site:
                raise provisioner.ProvisioningError("new-site failed: database error")
            return LISTED if "list-apps" in args else ""
        return calls, fake

    def test_does_nothing_when_switched_off(self):
        with patch.dict(frappe.local.conf, {"stemic_local_provisioner": 0}):
            self.assertEqual(provisioner.run(self.job), "disabled")
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", self.job, "status"), "Queued")

    def test_success_activates_school_and_stores_password(self):
        calls, fake = self.cli()
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertEqual(provisioner.run(self.job), "Succeeded")
        site = f"{self.slug}.localhost"
        new_site = next(c for c in calls if c[0] == "new-site")
        self.assertEqual(new_site[1], site)
        self.assertIn("school_erp", new_site)
        database = new_site[new_site.index("--db-name") + 1]
        self.assertEqual(database, "sch_" + self.slug.replace("-", "_"))  # named after the school, not random
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "database_name"), database)
        self.assertTrue(any("list-apps" in c for c in calls))  # readiness checked before success
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", self.job, "status"), "Succeeded")
        tenant = frappe.get_doc("SaaS Tenant", self.slug)
        self.assertEqual((tenant.status, tenant.canonical_site), ("Active", site))
        self.assertEqual(frappe.db.get_value("SaaS Domain", f"{self.slug}.stemic.test", "status"), "Active")
        access = api.site_access(self.slug)
        self.assertEqual(access["site"], site)
        self.assertTrue(access["password"] and access["password"] != "*" * len(access["password"]))
        self.assertEqual(provisioner.run(self.job), "Succeeded")  # a second run does nothing

    def test_a_site_on_a_real_domain_is_told_its_https_address(self):
        calls, fake = self.cli()
        with patch.dict(frappe.local.conf, {"stemic_site_domain": "stemic.test"}), \
                patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertEqual(provisioner.run(self.job), "Succeeded")
        site = f"{self.slug}.stemic.test"
        self.assertIn(("--site", site, "set-config", "host_name", f"https://{site}"), calls)
        self.assertLess(next(i for i, c in enumerate(calls) if "list-apps" in c),
                        next(i for i, c in enumerate(calls) if "host_name" in c))  # after the readiness check

    def test_a_development_site_keeps_plain_http(self):
        calls, fake = self.cli()
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertEqual(provisioner.run(self.job), "Succeeded")
        self.assertFalse(any("host_name" in c for c in calls))

    def test_failure_marks_job_and_school_failed(self):
        calls, fake = self.cli(fail_new_site=True)
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", side_effect=[False, True]):
            self.assertEqual(provisioner.run(self.job), "Failed")
        job = frappe.get_doc("SaaS Provisioning Job", self.job)
        self.assertEqual(job.status, "Failed")
        self.assertIn("database error", job.last_error)
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Failed")
        self.assertTrue(any(c[0] == "drop-site" for c in calls))  # the half-made site is cleaned up

    def test_an_existing_database_is_never_overwritten(self):
        calls, fake = self.cli()
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False), \
                patch.object(provisioner, "_database_exists", return_value=True):
            self.assertEqual(provisioner.run(self.job), "Failed")
        self.assertFalse([c for c in calls if c[0] in ("new-site", "drop-site")])  # nothing created, nothing dropped
        self.assertIn("already exists", frappe.db.get_value("SaaS Provisioning Job", self.job, "last_error"))

    def test_database_names_fit_mariadb(self):
        self.assertEqual(provisioner.database_name("nyeri-high"), "sch_nyeri_high")
        self.assertLessEqual(len(provisioner.database_name("a" + "b" * 48)), 64)

    def test_secrets_are_scrubbed_from_command_output(self):
        result = SimpleNamespace(stdout="Access denied using password root-secret-123", stderr="", returncode=1)
        frappe.flags.stemic_cli_in_tests = True  # subprocess.run is mocked below; nothing real runs
        try:
            with patch("subprocess.run", return_value=result):
                with self.assertRaises(provisioner.ProvisioningError) as caught:
                    provisioner._frappe_cli("new-site", "x.localhost", secrets_=("root-secret-123",))
        finally:
            frappe.flags.stemic_cli_in_tests = False
        self.assertNotIn("root-secret-123", str(caught.exception))
        self.assertIn("********", str(caught.exception))

    def test_tests_cannot_run_the_real_cli(self):
        with patch("subprocess.run") as run:
            self.assertRaises(provisioner.ProvisioningError, provisioner._frappe_cli, "new-site", "x.localhost")
        run.assert_not_called()

    def test_demo_schools_are_never_provisioned(self):
        frappe.db.set_value("SaaS Tenant", self.slug, "notes", provisioner.DEMO_NOTE)
        with patch.object(provisioner, "_frappe_cli") as cli:
            self.assertEqual(provisioner.run(self.job), "refused")
        cli.assert_not_called()
        job = frappe.db.get_value("SaaS Provisioning Job", self.job, ["status", "last_error"], as_dict=True)
        self.assertEqual(job.status, "Failed")  # not left Queued with no reason (it used to be skipped silently)
        self.assertIn("demo school", job.last_error)
        self.assertIn("demo school", " ".join(api.provisioning_progress(self.slug)["job"]["reasons"]))
        self.assertRaises(frappe.ValidationError, api.queue_provisioning, self.slug, "demo-" + frappe.generate_hash(length=10))

    def test_manual_success_still_blocked(self):
        api.record_job_result(self.job, "Running")
        self.assertRaises(frappe.ValidationError, api.record_job_result, self.job, "Succeeded")

    def test_an_abandoned_build_is_failed_and_its_half_made_site_removed(self):
        """A worker that died mid-build (e.g. the machine restarted) leaves a Running job and part of a site."""
        frappe.db.set_value("SaaS Provisioning Job", self.job, "status", "Running")
        old = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-(provisioner.STALE_RUNNING + 5))
        frappe.db.sql("UPDATE `tabSaaS Provisioning Job` SET modified = %s WHERE name = %s", (old, self.job))
        calls, fake = self.cli()
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=True):
            provisioner.process_queue()
        self.assertEqual([c[:2] for c in calls if c[0] == "drop-site"], [("drop-site", f"{self.slug}.localhost")])
        job = frappe.db.get_value("SaaS Provisioning Job", self.job, ["status", "last_error"], as_dict=True)
        self.assertEqual(job.status, "Failed")
        self.assertIn(f"The partly created site {self.slug}.localhost was removed", job.last_error)
        progress = api.provisioning_progress(self.slug)["job"]
        self.assertIn("was removed", progress["cleanup"])  # the dialog says what became of it

    def test_operator_mark_failed_while_running_is_respected(self):
        def fake(*args, **kwargs):
            if args[0] == "new-site":  # an operator gives up on the job while the site is still being built
                api.record_job_result(self.job, "Failed", "Stopped by an operator")
            return LISTED if "list-apps" in args else ""
        with patch.object(provisioner, "_frappe_cli", side_effect=fake), patch.object(provisioner, "_site_dir_exists", return_value=False):
            self.assertEqual(provisioner.run(self.job), "Closed by operator")
        self.assertEqual(frappe.db.get_value("SaaS Provisioning Job", self.job, "status"), "Failed")
        self.assertEqual(frappe.db.get_value("SaaS Tenant", self.slug, "status"), "Failed")

    def test_manual_buttons(self):
        # Provision Now on a Pending school hands its queued job over
        self.assertEqual(api.provision_tenant_now(self.slug)["job"], self.job)
        provisioner.enqueue.assert_called_with(self.job)
        # Process Queue Now hands over real schools' queued jobs and skips demo ones
        provisioner.enqueue.reset_mock()
        handed = api.process_queue_now()["handed_to_worker"]
        self.assertGreaterEqual(handed, 1)
        self.assertIn(self.job, [c.args[0] for c in provisioner.enqueue.call_args_list])
        frappe.db.set_value("SaaS Tenant", self.slug, "notes", provisioner.DEMO_NOTE)
        provisioner.enqueue.reset_mock()
        api.process_queue_now()
        self.assertNotIn(self.job, [c.args[0] for c in provisioner.enqueue.call_args_list])
        # nothing queued: say so instead of failing silently
        frappe.db.set_value("SaaS Provisioning Job", self.job, "status", "Failed")
        self.assertRaises(frappe.ValidationError, api.provision_tenant_now, self.slug)


class TestSiteStatus(TestCase):
    """The Open Site dialog's data: read-only, platform admins only, never a password."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.slug = "stat-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Status School", self.slug, "head@status.test")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_status_of_a_site_on_this_bench(self):
        from stemic_control import site_runtime

        site = frappe.local.site  # a site that really is on this bench: the one the tests run on
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", site)
        with patch.object(site_runtime, "servers", return_value=[{"port": 8000, "site": None}, {"port": 8009, "site": "other.localhost"}]), \
                patch.object(site_runtime, "_ping", return_value=True) as ping:
            status = site_runtime.site_status(self.slug)
        self.assertTrue(status["on_this_bench"])
        self.assertEqual(status["served_at"][0]["url"], f"http://{site}:8000")
        self.assertEqual(ping.call_count, 1)  # the server pinned to another site is not asked
        self.assertEqual(status["database"]["name"], frappe.conf.db_name)
        self.assertGreater(status["database"]["tables"], 0)
        self.assertNotIn("password", str(status).lower())

    def test_site_elsewhere_and_who_may_ask(self):
        from stemic_control import site_runtime

        self.assertRaises(frappe.ValidationError, site_runtime.site_status, self.slug)  # no site yet
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", "nowhere-" + self.slug + ".localhost")
        with patch.object(site_runtime, "servers", return_value=[]):
            self.assertEqual(site_runtime.site_status(self.slug)["on_this_bench"], False)
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", "../../etc")
        self.assertRaises(frappe.ValidationError, site_runtime.site_status, self.slug)  # not a host name
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, site_runtime.site_status, self.slug)


class TestSiteOperations(TestCase):
    """Backup / Migrate / Clear Cache run from the Open Site dialog: only those, only here, one at a time, on record."""

    def setUp(self):
        frappe.set_user("Administrator")
        self._conf = patch.dict(frappe.local.conf, {"stemic_provision_environment": "development",
                                                    "stemic_provision_allowed_benches": [get_bench_path()]})
        self._conf.start()
        from stemic_control import site_runtime

        self.slug = "ops-" + frappe.generate_hash(length=6).lower()
        self.site = f"{self.slug}.localhost"
        api.register_tenant("Operations School", self.slug, "head@ops.test")
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", self.site)
        # its folder is the site the tests run on: a real folder and site_config on this bench
        real = site_runtime._site_dir(frappe.local.site)
        self._dir = patch.object(site_runtime, "_site_dir", side_effect=lambda site: real if site == self.site else f"/nonexistent/{site}")
        self._dir.start()

    def tearDown(self):
        self._dir.stop()
        self._conf.stop()
        frappe.set_user("Administrator")

    def test_run_is_queued_recorded_and_one_at_a_time(self):
        from stemic_control import site_runtime

        with patch.object(frappe, "enqueue") as enqueue:
            op = site_runtime.run_operation(self.slug, "Backup")["operation"]
            self.assertEqual(enqueue.call_args.kwargs["operation"], op)
            self.assertRaises(frappe.ValidationError, site_runtime.run_operation, self.slug, "Migrate")  # Backup is queued
        row = frappe.db.get_value("SaaS Site Operation", op, ["site", "action", "status", "requested_by"], as_dict=True)
        self.assertEqual((row.site, row.action, row.status, row.requested_by), (self.site, "Backup", "Queued", "Administrator"))
        self.assertRaises(frappe.ValidationError, site_runtime.run_operation, self.slug, "Drop Site")  # only the listed actions

        with patch.object(site_runtime, "_set", side_effect=lambda op_, v: frappe.db.set_value("SaaS Site Operation", op_, v)), \
                patch.object(provisioner, "_frappe_cli", return_value="Database: /x/db.sql.gz 1.0MiB\nConfig  : /x/c.json") as cli:
            self.assertEqual(site_runtime.perform_operation(op), "Succeeded")
        self.assertEqual(cli.call_args.args, ("--site", self.site, "backup", "--with-files"))
        self.assertIn("Database: /x/db.sql.gz", frappe.db.get_value("SaaS Site Operation", op, "summary"))
        self.assertEqual(site_runtime.perform_operation(op), "Succeeded")  # already done: not run again

    def test_failure_is_recorded_without_passwords(self):
        from stemic_control import site_runtime

        with patch.object(frappe, "enqueue"):
            op = site_runtime.run_operation(self.slug, "Migrate")["operation"]
        secret = frappe.conf.db_password
        with patch.object(site_runtime, "_set", side_effect=lambda op_, v: frappe.db.set_value("SaaS Site Operation", op_, v)), \
                patch.object(provisioner, "_frappe_cli", side_effect=provisioner.ProvisioningError(f"failed using {secret}")):
            self.assertEqual(site_runtime.perform_operation(op), "Failed")
        row = frappe.db.get_value("SaaS Site Operation", op, ["status", "output"], as_dict=True)
        self.assertEqual(row.status, "Failed")
        self.assertNotIn(secret, row.output)

    def test_who_and_where_may_run(self):
        from stemic_control import site_runtime

        with patch.dict(frappe.local.conf, {"stemic_provision_allowed_benches": ["/srv/other-bench"]}):
            self.assertRaises(frappe.ValidationError, site_runtime.run_operation, self.slug, "Backup")
        frappe.db.set_value("SaaS Tenant", self.slug, "canonical_site", "elsewhere.localhost")
        self.assertRaises(frappe.ValidationError, site_runtime.run_operation, self.slug, "Backup")  # not on this bench
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, site_runtime.run_operation, self.slug, "Backup")
        frappe.set_user("Administrator")
        forged = frappe.get_doc({"doctype": "SaaS Site Operation", "tenant": self.slug, "site": "x", "action": "Backup"})
        self.assertRaises(frappe.PermissionError, forged.insert, ignore_permissions=True)  # only through run_operation

    def test_reset_admin_password_sets_and_stores_it_but_never_shows_it(self):
        from frappe.utils.password import get_decrypted_password

        from stemic_control import site_runtime

        with patch.object(frappe, "enqueue"):
            op = site_runtime.run_operation(self.slug, "Reset Admin Password")["operation"]
        with patch.object(site_runtime, "_set", side_effect=lambda op_, v: frappe.db.set_value("SaaS Site Operation", op_, v)), \
                patch.object(provisioner, "_frappe_cli", side_effect=lambda *a, **k: f"Password updated to {a[-1]}") as cli:
            self.assertEqual(site_runtime.perform_operation(op), "Succeeded")
        args = cli.call_args.args
        self.assertEqual(args[:3], ("--site", self.site, "set-admin-password"))
        self.assertGreaterEqual(len(args[3]), 16)  # a fresh random password
        self.assertEqual(get_decrypted_password("SaaS Tenant", self.slug, "site_admin_password"), args[3])
        self.assertNotIn(args[3], frappe.db.get_value("SaaS Site Operation", op, "output"))

    def test_link_an_existing_site(self):
        from stemic_control import site_runtime
        from stemic_control.tests.helpers import make_eligible

        school = "lnk-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Linked School", school, "head@linked.test")
        free = patch.object(site_runtime, "unlinked_sites", return_value=[self.site + ".free"])
        ready = patch.object(provisioner, "check_ready")
        with free, ready:
            self.assertRaises(frappe.ValidationError, site_runtime.link_existing_site, school, self.site + ".free")  # not approved
            make_eligible(school)
            self.assertRaises(frappe.ValidationError, site_runtime.link_existing_site, school, "not-free.localhost")
            out = site_runtime.link_existing_site(school, self.site + ".free")
            self.assertEqual(out["status"], "Active")
            self.assertEqual(frappe.db.get_value("SaaS Tenant", school, "canonical_site"), self.site + ".free")
            self.assertRaises(frappe.ValidationError, site_runtime.link_existing_site, school, self.site + ".free")  # has a site now


class TestSecrets(TestCase):
    """Secrets come from the environment first (a protected file loaded by supervisor / systemd), then site_config."""

    def test_the_environment_wins_over_site_config(self):
        import os

        from stemic_control import config

        with patch.dict(frappe.local.conf, {"stemic_db_root_password": "from-site-config"}):
            self.assertEqual(config.secret("stemic_db_root_password"), ("from-site-config", "site_config"))
            with patch.dict(os.environ, {"STEMIC_DB_ROOT_PASSWORD": "from-env", "STEMIC_DB_ROOT_USERNAME": "stemic_provisioner"}):
                self.assertEqual(config.secret("stemic_db_root_password"), ("from-env", "environment"))
                self.assertEqual(provisioner._root_args(), ["--db-root-username", "stemic_provisioner", "--db-root-password", "from-env"])
        with patch.dict(frappe.local.conf, {"stemic_db_root_password": None, "root_password": None}), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STEMIC_DB_ROOT_PASSWORD", None)
            self.assertEqual(config.secret("stemic_db_root_password"), (None, None))
            self.assertRaises(provisioner.ProvisioningError, provisioner._root_password)

    def test_new_site_runs_as_the_configured_account(self):
        import os

        from stemic_control.tests.helpers import make_eligible, remove_school

        slug = "sec-" + frappe.generate_hash(length=6).lower()
        api.register_tenant("Secrets School", slug, "head@secrets.test")
        make_eligible(slug)
        conf = {"stemic_platform_domain": "stemic.test", "stemic_local_provisioner": 1, "stemic_site_domain": "localhost",
                "stemic_provision_environment": "development", "stemic_provision_allowed_benches": [get_bench_path()]}
        calls = []
        try:
            with patch.dict(frappe.local.conf, conf), patch.object(provisioner, "enqueue"), \
                    patch.dict(os.environ, {"STEMIC_DB_ROOT_USERNAME": "stemic_provisioner", "STEMIC_DB_ROOT_PASSWORD": "env-secret"}), \
                    patch.object(provisioner, "_frappe_cli", side_effect=lambda *a, **k: calls.append((a, k)) or (LISTED if "list-apps" in a else "")), \
                    patch.object(provisioner, "_site_dir_exists", return_value=False), patch.object(provisioner, "_database_exists", return_value=False):
                job = api.queue_provisioning(slug, "sec-" + frappe.generate_hash(length=12))
                self.assertEqual(provisioner.run(job), "Succeeded")
            new_site, kwargs = next((a, k) for a, k in calls if a[0] == "new-site")
            self.assertEqual(new_site[new_site.index("--db-root-username") + 1], "stemic_provisioner")
            self.assertIn("env-secret", kwargs["secrets_"])  # and it is scrubbed from any output
        finally:
            remove_school(slug)

    def test_setup_check_says_where_secrets_come_from(self):
        import os

        from stemic_control import setup_check

        with patch.dict(frappe.local.conf, {"stemic_db_root_password": "in-site-config", "stemic_provision_environment": "development"}):
            os.environ.pop("STEMIC_DB_ROOT_PASSWORD", None)
            item = next(i for i in setup_check._secret_sources() if i["label"] == "Db root password")
            self.assertIsNone(item["ok"])  # development: a note, not a failure
            with patch.dict(frappe.local.conf, {"stemic_provision_environment": "production"}):
                item = next(i for i in setup_check._secret_sources() if i["label"] == "Db root password")
                self.assertFalse(item["ok"])  # production: site_config is not good enough
            with patch.dict(os.environ, {"STEMIC_DB_ROOT_PASSWORD": "from-env"}):
                item = next(i for i in setup_check._secret_sources() if i["label"] == "Db root password")
                self.assertTrue(item["ok"])
                self.assertNotIn("from-env", str(item))  # the value is never shown
