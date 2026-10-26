"""Local provisioner: turns queued Create Site jobs into real school sites on this bench.

For development and single-server setups only. It runs Frappe's own CLI (`new-site`, `list-apps`, `drop-site`)
in a subprocess, so the admin site's worker needs filesystem access to the bench and the database root password.
A production provisioner should run on separate infrastructure with its own credentials.

Admin site_config.json:
    stemic_local_provisioner   1 to enable (nothing runs without it)
    stemic_db_root_password    MariaDB root password used to create school databases
    stemic_site_domain         school sites are "<slug>.<this>"; default "localhost"
    stemic_site_apps           apps installed on each school site; default ["erpnext", "school_erp"]
    stemic_bench_path          bench to create sites in; default: this bench
"""

import os
import secrets
import subprocess

import frappe
from frappe.utils import add_to_date, get_bench_path, now_datetime

from stemic_control import policy

DEFAULT_APPS = ["erpnext", "school_erp"]
NEW_SITE_TIMEOUT = 45 * 60  # installing ERPNext can take several minutes
STALE_RUNNING = 90  # minutes before a Running job is treated as abandoned
DEMO_NOTE = "Demo data (stemic_control.demo)"


class ProvisioningError(Exception):
    pass


def enabled() -> bool:
    return bool(frappe.conf.get("stemic_local_provisioner"))


def site_name(slug: str) -> str:
    return f"{slug}.{(frappe.conf.get('stemic_site_domain') or 'localhost').strip('.')}"


def _apps() -> list[str]:
    return list(frappe.conf.get("stemic_site_apps") or DEFAULT_APPS)


def _bench() -> str:
    return frappe.conf.get("stemic_bench_path") or get_bench_path()


def _root_password() -> str:
    password = frappe.conf.get("stemic_db_root_password") or frappe.conf.get("root_password")
    if not password:
        raise ProvisioningError("Set stemic_db_root_password in the admin site's site_config.json")
    return password


def _frappe_cli(*args, timeout=600, secrets_=()) -> str:
    """Run `frappe <args>` the way bench does, from the bench's sites folder. Returns output; raises with a scrubbed tail."""
    bench = _bench()
    cmd = [os.path.join(bench, "env", "bin", "python"), "-m", "frappe.utils.bench_helper", "frappe", *args]
    try:
        result = subprocess.run(cmd, cwd=os.path.join(bench, "sites"), capture_output=True, text=True, timeout=timeout)
        output, code = (result.stdout or "") + (result.stderr or ""), result.returncode
    except subprocess.TimeoutExpired as e:
        output, code = f"{e.stdout or ''}{e.stderr or ''}\nTimed out after {timeout}s", -1
    for secret in secrets_:
        if secret:
            output = output.replace(secret, "********")
    if code != 0:
        raise ProvisioningError(f"`frappe {args[0] if args[0] != '--site' else ' '.join(args[:3])}` failed:\n{output[-3000:]}")
    return output


def check_ready(site: str) -> None:
    """Independent readiness check: the site answers on its own database and lists every required app."""
    listed = _frappe_cli("--site", site, "list-apps", timeout=120)
    installed = {line.split()[0] for line in listed.splitlines() if line.strip() and not line.startswith(" ")}
    missing = [app for app in ["frappe", *_apps()] if app not in installed]
    if missing:
        raise ProvisioningError(f"Site {site} is missing apps: {', '.join(missing)}")


def _set_job(job, status, error=None):
    updates = {"status": status}
    if status == "Running":
        updates["attempts"] = (frappe.db.get_value("SaaS Provisioning Job", job, "attempts") or 0) + 1
    if status == "Failed":
        updates["last_error"] = (error or "Failed without a message")[:10000]
    frappe.db.set_value("SaaS Provisioning Job", job, updates)


def _set_tenant(tenant, status, **values):
    doc = frappe.get_doc("SaaS Tenant", tenant)
    doc.update(values)
    if doc.status != status:
        doc.status = status
    doc.flags.ignore_permissions = True
    doc.save()


def run(job: str) -> str:
    """Provision one queued Create Site job (in a background worker). Safe to call repeatedly: only a Queued job is
    picked up. Not whitelisted: the API queues it (api.provision_now) rather than running it inside a web request."""
    if not enabled():
        return "disabled"

    row = frappe.db.get_value("SaaS Provisioning Job", job, ["name", "tenant", "action", "status"], as_dict=True, for_update=True)
    if not row or row.status != "Queued" or row.action != "Create Site":
        return row.status if row else "missing"
    tenant = frappe.get_doc("SaaS Tenant", row.tenant)
    if tenant.notes == DEMO_NOTE:
        return "skipped (demo school)"

    site = site_name(tenant.slug)
    _set_job(job, "Running")
    _set_tenant(tenant.name, "Provisioning")
    frappe.db.commit()

    created = False
    password = None
    try:
        root = _root_password()
        if os.path.isdir(os.path.join(_bench(), "sites", site)):
            raise ProvisioningError(f"Site {site} already exists on this bench; refusing to overwrite it")
        password = secrets.token_urlsafe(14)
        args = ["new-site", site, "--db-root-password", root, "--admin-password", password]
        for app in _apps():
            args += ["--install-app", app]
        created = True
        _frappe_cli(*args, timeout=NEW_SITE_TIMEOUT, secrets_=(root, password))
        check_ready(site)
    except Exception as e:
        frappe.db.rollback()
        message = str(e) if isinstance(e, ProvisioningError) else frappe.get_traceback()
        if created:
            message += _drop_partial_site(site)
        _set_job(job, "Failed", message)
        _set_tenant(tenant.name, "Failed")
        frappe.db.commit()
        frappe.log_error(title=f"Provisioning failed for {tenant.name}", message=message)
        return "Failed"

    # An operator may have marked the job Failed while it ran (e.g. thinking the worker was stuck): their call stands
    if frappe.db.get_value("SaaS Provisioning Job", job, "status", for_update=True) != "Running":
        frappe.log_error(title=f"Provisioning of {tenant.name} finished after the job was closed",
                         message=f"Site {site} was created and passed its checks, but {job} is no longer Running. "
                                 "Review it: drop the site or queue the school again.")
        frappe.db.commit()
        return "Closed by operator"

    base = frappe.conf.get("stemic_platform_domain") or "stemischools.com"
    subdomain = f"{tenant.slug}.{base}"
    _set_job(job, "Succeeded")
    _set_tenant(tenant.name, "Active", canonical_site=site, site_admin_password=password,  # Password field: saved encrypted
                primary_domain=tenant.primary_domain or (subdomain if frappe.db.exists("SaaS Domain", subdomain) else None))
    if frappe.db.get_value("SaaS Domain", subdomain, "status") == "Verified":
        frappe.db.set_value("SaaS Domain", subdomain, {"status": "Active", "is_primary": 1})
    frappe.db.commit()
    return "Succeeded"


def _drop_partial_site(site) -> str:
    """Remove what a failed new-site left behind so the school can be retried cleanly."""
    if not os.path.isdir(os.path.join(_bench(), "sites", site)):
        return ""
    try:
        _frappe_cli("drop-site", site, "--db-root-password", _root_password(), "--no-backup", "--force",
                    timeout=600, secrets_=(_root_password(),))
        return f"\n\nThe partly created site {site} was removed."
    except Exception as e:
        return f"\n\nCould not remove the partly created site {site}: {e}"


def enqueue(job: str):
    """Hand a job to a background worker (long queue) once the request that queued it has committed."""
    if enabled():
        frappe.enqueue("stemic_control.provisioner.run", queue="long", timeout=NEW_SITE_TIMEOUT + 600, job=job,
                       enqueue_after_commit=True, job_id=f"stemic-provision-{job}", deduplicate=True)


def process_queue() -> int:
    """Scheduler safety net: pick up jobs no worker took, and fail jobs a dead worker left Running.
    Returns how many jobs were handed to a worker (the Process Queue Now button reports it)."""
    if not enabled():
        return 0
    cutoff = add_to_date(now_datetime(), minutes=-STALE_RUNNING)
    for name in frappe.get_all("SaaS Provisioning Job", filters={"status": "Running", "action": "Create Site",
                                                                  "modified": ("<", cutoff)}, pluck="name"):
        _set_job(name, "Failed", f"No progress for {STALE_RUNNING} minutes; the worker probably stopped. Queue it again.")
        tenant = frappe.db.get_value("SaaS Provisioning Job", name, "tenant")
        if policy.can_move(policy.TENANT_TRANSITIONS, frappe.db.get_value("SaaS Tenant", tenant, "status"), "Failed"):
            _set_tenant(tenant, "Failed")
    frappe.db.commit()
    demo = set(frappe.get_all("SaaS Tenant", filters={"notes": DEMO_NOTE}, pluck="name"))
    handed = 0
    for job in frappe.get_all("SaaS Provisioning Job", filters={"status": "Queued", "action": "Create Site"},
                              fields=["name", "tenant"], order_by="creation"):
        if job.tenant not in demo:
            enqueue(job.name)
            handed += 1
    return handed
