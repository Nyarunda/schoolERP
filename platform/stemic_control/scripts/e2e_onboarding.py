"""End-to-end acceptance test of Stemic school onboarding, on a real bench and a real new site.

    register -> approve -> plan, subscription, invoice, payment -> queue -> provision (bench new-site)
    -> domain active -> site answers -> issue license -> school Administrator logs in -> key accepted,
    licensed modules visible, others hidden -> clean up (drop the site and its records)

It builds and drops a real site (a few minutes): run it on a development or staging bench whose admin site has the
local provisioner switched on and an authorised environment (stemic_provision_environment and
stemic_provision_allowed_benches). If no running web server serves the new site (bench start's is pinned to the
bench's default_site, if one is set), the run starts one for it on a free port and stops it at the end.

    cd frappe-bench/sites
    ../env/bin/python ../apps/stemic_control/scripts/e2e_onboarding.py admin.localhost          # run, then clean up
    ../env/bin/python ../apps/stemic_control/scripts/e2e_onboarding.py admin.localhost --keep   # leave the site to look at
    ../env/bin/python ../apps/stemic_control/scripts/e2e_onboarding.py admin.localhost --cleanup <run-id>

Exit status: 0 every step passed; 1 a step failed (the run id is printed so --cleanup can remove what it left).
"""

import sys
import time
import traceback

SITE = sys.argv[1] if len(sys.argv) > 1 else "admin.localhost"
LICENSED = ["fees", "exams"]  # the plan's modules: these must be visible on the new site, the rest hidden
HIDDEN_PROBE = "Transport Route"  # a DocType of a module the plan leaves out
VISIBLE_PROBE = "Fee Type"  # ... and one of a module it includes
RUN = None
steps = []


def step(name):
    def wrap(fn):
        def inner(*a, **k):
            start = time.time()
            try:
                out = fn(*a, **k)
            except Exception as e:
                steps.append((name, False, f"{type(e).__name__}: {str(e)[:300]}", time.time() - start))
                print(f"  FAIL  {name}: {type(e).__name__}: {str(e)[:300]}", flush=True)
                raise
            note = out[-1] if isinstance(out, tuple) else out  # a step may hand something on, then say what it did
            steps.append((name, True, note or "", time.time() - start))
            print(f"  ok    {name}" + (f": {note}" if note else "") + f"  ({time.time() - start:.1f}s)", flush=True)
            return out
        return inner
    return wrap


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def slug():
    return f"e2e-{RUN}"


# ----------------------------------------------------------------------------- the journey
@step("Register the school and claim its subdomain")
def register(frappe):
    from stemic_control import api

    tenant = api.register_tenant(f"E2E School {RUN}", slug(), f"head@{slug()}.test")
    sub = api.request_domain(tenant, f"{tenant}.{api.platform_domain()}")
    check(sub["status"] == "Verified", f"the platform subdomain should be verified at once, got {sub['status']}")
    frappe.db.commit()
    return f"{tenant}, {sub['hostname']}"


@step("An operator approves it")
def approve(frappe):
    from stemic_control import api, onboarding

    try:
        api.queue_provisioning(slug(), f"e2e-{RUN}-early")
    except frappe.ValidationError:
        frappe.db.rollback()
    else:
        raise AssertionError("an unapproved school was queued")
    onboarding.submit_for_approval(slug())
    onboarding.approve_tenant(slug(), "End-to-end test")
    frappe.db.commit()
    return frappe.db.get_value("SaaS Tenant", slug(), "status")


@step("Plan, subscription, invoice and full payment")
def pay(frappe):
    from stemic_control import billing, onboarding

    plan = f"E2E Plan {RUN}"
    frappe.get_doc({"doctype": "SaaS Plan", "plan_name": plan, "enabled": 1, "monthly_price": 1000,
                    "student_limit": 50, "modules": frappe.as_json(LICENSED)}).insert()
    sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": slug(), "plan": plan,
                          "starts_on": frappe.utils.nowdate()}).insert().name
    frappe.db.commit()
    check(onboarding.commercial_basis(slug()) is None, "an unpaid trial counted as commercially eligible")
    invoice = billing.create_invoice(sub, months=1)
    total = frappe.db.get_value("SaaS Invoice", invoice, "total")
    billing.record_payment(invoice, total, "M-Pesa", f"QE2E{RUN.upper()}")
    frappe.db.commit()
    check(frappe.db.get_value("SaaS Subscription", sub, "status") == "Active", "payment did not make the subscription Active")
    check(onboarding.commercial_basis(slug()) == "Paid subscription", "a paid subscription was not eligible")
    return f"{sub} Active, {invoice} paid ({total:,.0f})"


@step("Queue and provision the site (bench new-site)")
def provision(frappe):
    from unittest.mock import patch

    from stemic_control import api, provisioner

    with patch.object(provisioner, "enqueue"):  # this script is the worker, so a real one does not race it
        job = api.queue_provisioning(slug(), f"e2e-{RUN}-create")
    frappe.db.commit()
    result = provisioner.run(job)
    error = frappe.db.get_value("SaaS Provisioning Job", job, "last_error") or ""
    check(result == "Succeeded", f"provisioning {result}: {error.splitlines()[-1] if error else ''}")
    t = frappe.db.get_value("SaaS Tenant", slug(), ["status", "canonical_site", "database_name", "primary_domain"], as_dict=True)
    check(t.status == "Active", f"the school is {t.status}")
    check(t.database_name == provisioner.database_name(slug()), f"database {t.database_name}")
    check(frappe.db.get_value("SaaS Provisioning Job", job, "environment") == frappe.conf.stemic_provision_environment,
          "the job did not record its environment")
    check(frappe.db.get_value("SaaS Domain", t.primary_domain, "status") == "Active", "the subdomain is not Active")
    return f"{t.canonical_site}, database {t.database_name}, domain {t.primary_domain}"


server = None  # a web server this run started for its site, stopped at the end


def _serve(site):
    """Serve the new site on a free port for the rest of the run (when no running server serves it: e.g. bench
    start's server is pinned to a default_site)."""
    import socket
    import subprocess

    import requests

    from stemic_control import provisioner

    global server
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    bench = provisioner._bench()
    server = subprocess.Popen([f"{bench}/env/bin/python", "-m", "frappe.utils.bench_helper", "frappe", "--site", site,
                               "serve", "--port", str(port), "--noreload"], cwd=f"{bench}/sites",
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(1)
        try:
            if requests.get(f"http://127.0.0.1:{port}/api/method/ping", timeout=2).ok:
                return port
        except requests.RequestException:
            pass
    raise AssertionError(f"a server for {site} did not start on port {port}")


@step("The site is running and its status agrees")
def running(frappe):
    from stemic_control import site_runtime

    s = site_runtime.site_status(slug())
    check(s["on_this_bench"], "the site is not on this bench")
    check(s["database"].get("name") == frappe.db.get_value("SaaS Tenant", slug(), "database_name"),
          f"site_config says {s['database'].get('name')}")
    check({"frappe", "erpnext", "school_erp"} <= {a["app"] for a in s["database"].get("apps", [])}, "apps missing")
    note = ""
    if not s["served_at"]:
        port = _serve(s["site"])
        s = site_runtime.site_status(slug())  # the status must now see the server just started for it
        check(any(f":{port}" in x["url"] for x in s["served_at"]), f"status did not see the server on port {port}")
        note = " (no running server served it; started one for this run)"
    return s["served_at"][0]["url"], s["served_at"][0]["url"] + note


@step("Issue the license")
def license_key(frappe):
    from stemic_control import api

    sub = frappe.db.get_value("SaaS Subscription", {"tenant": slug()})
    name = api.issue_license(sub)["license"]
    frappe.db.commit()
    lic = frappe.db.get_value("SaaS License", name, ["status", "site", "signed_key"], as_dict=True)
    check(lic.status == "Issued" and lic.site == frappe.db.get_value("SaaS Tenant", slug(), "canonical_site"), "license not issued to the site")
    return name


@step("The school's Administrator logs in and installs the key")
def school_login(frappe, url):
    import requests

    from stemic_control import api

    access = api.site_access(slug())
    session = requests.Session()
    login = session.post(f"{url}/api/method/login", data={"usr": access["user"], "pwd": access["password"]}, timeout=30)
    check(login.status_code == 200, f"login refused ({login.status_code})")
    key = frappe.db.get_value("SaaS License", {"tenant": slug(), "status": "Issued"}, "signed_key")
    # what the License tab's Install Key does: a new school has not filled in School Settings yet
    saved = session.post(f"{url}/api/method/school_erp.licensing.install_key", data={"key": key}, timeout=60)
    check(saved.status_code == 200, f"installing the key failed ({saved.status_code}): {saved.text[:200]}")
    overview = session.get(f"{url}/api/method/school_erp.licensing.license_overview", timeout=30).json()["message"]
    check(overview["status"] == "valid", f"the school sees the key as {overview['status']}: {overview.get('message')}")
    check(set(LICENSED) <= set(overview["modules"]), f"modules on the site: {overview['modules']}")
    return session, f"license {overview['status']}, modules {', '.join(m for m in overview['modules'] if m != 'core')}"


@step("Licensed modules are visible; the others are hidden")
def visibility(frappe, url, session):
    import json
    import re

    # what the desk offers this user: the boot embedded in /app (search, list routes and link fields use it)
    desk = session.get(f"{url}/app", timeout=60)
    found = re.search(r'"can_read":\s*(\[[^\]]*\])', desk.text)
    check(desk.status_code == 200 and found, f"could not read the desk's boot ({desk.status_code})")
    can_read = json.loads(found.group(1))
    check(VISIBLE_PROBE in can_read, f"{VISIBLE_PROBE} (a licensed module) is not offered to the school")
    check(HIDDEN_PROBE not in can_read, f"{HIDDEN_PROBE} (not licensed) is still offered to the school")
    report = session.get(f"{url}/api/method/frappe.desk.query_report.run", params={"report_name": "Transport List"}, timeout=30)
    check(report.status_code != 200, "the Transport List report ran without the Transport module")
    return f"{VISIBLE_PROBE} visible, {HIDDEN_PROBE} and its report hidden"


# ----------------------------------------------------------------------------- cleanup
def cleanup(frappe):
    """Drop the run's site and remove its records, and nothing else."""
    from stemic_control import provisioner

    if server:
        server.terminate()
        server.wait(timeout=30)
    s = slug()
    site = frappe.db.get_value("SaaS Tenant", s, "canonical_site") or provisioner.site_name(s)
    if provisioner._site_dir_exists(site):
        try:
            provisioner._frappe_cli("drop-site", site, "--db-root-password", provisioner._root_password(), "--no-backup",
                                    "--force", timeout=600, secrets_=(provisioner._root_password(),))
            print(f"  dropped {site}")
        except Exception as e:
            print(f"  could not drop {site}: {e}")
    frappe.db.rollback()
    subs = frappe.get_all("SaaS Subscription", filters={"tenant": s}, pluck="name") or [""]
    invoices = frappe.get_all("SaaS Invoice", filters={"tenant": s}, pluck="name") or [""]
    for dt, f in (("SaaS License", {"tenant": s}), ("SaaS Commission", {"tenant": s}), ("SaaS Payment", {"invoice": ("in", invoices)}),
                  ("SaaS Invoice", {"name": ("in", invoices)}), ("SaaS Site Operation", {"tenant": s}),
                  ("SaaS Provisioning Job", {"tenant": s}), ("SaaS Domain", {"tenant": s}),
                  ("SaaS Subscription", {"name": ("in", subs)}), ("SaaS Tenant", {"name": s}),
                  ("SaaS Plan", {"name": f"E2E Plan {RUN}"})):
        frappe.db.delete(dt, f)
    frappe.db.commit()
    print(f"  removed the records of run {RUN}")


def main():
    global RUN
    import frappe

    frappe.init(SITE, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    if sys.argv[2:3] == ["--cleanup"]:
        RUN = (sys.argv[3:4] or [""])[0].strip().lower()
        if not RUN.isalnum():
            sys.exit("usage: e2e_onboarding.py <admin site> --cleanup <run-id>")
        cleanup(frappe)
        return
    keep = "--keep" in sys.argv[2:]
    RUN = frappe.generate_hash(length=6).lower()
    print(f"run {RUN} on {SITE}: school {slug()}", flush=True)
    started, failed = time.time(), False
    try:
        register(frappe)
        approve(frappe)
        pay(frappe)
        provision(frappe)
        url, _ = running(frappe)
        license_key(frappe)
        session, _ = school_login(frappe, url)
        visibility(frappe, url, session)
    except Exception:
        failed = True
        traceback.print_exc(limit=3)
    finally:
        if keep:
            if server:
                server.terminate()
            print(f"\nkept: run {RUN}; remove it with --cleanup {RUN}")
        else:
            print("\ncleaning up")
            cleanup(frappe)
    print(f"\n{'FAIL' if failed else 'PASS'}: {sum(ok for _n, ok, *_ in steps)} of {len(steps)} steps passed in {time.time() - started:.0f}s")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
