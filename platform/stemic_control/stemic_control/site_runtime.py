"""How a school's site is doing on this bench: is it being served (and where), its database, apps, use and backups.

Read-only. It reads the site's own site_config.json and connects with the site's own database credentials (as the
site itself does); the password is never returned. A site on another server is reported as not on this bench.
"""

import datetime
import glob
import json
import os
import re

import frappe
from frappe.utils import flt

PING_TIMEOUT = 1.5
SITE_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}$")


def _site_dir(site):
    from stemic_control import provisioner

    return os.path.join(provisioner._bench(), "sites", site)


def _config(site):
    """The site's site_config.json over the bench's common one, as Frappe merges them."""
    folder = _site_dir(site)
    conf = {}
    for path in (os.path.join(os.path.dirname(folder), "common_site_config.json"), os.path.join(folder, "site_config.json")):
        try:
            with open(path) as f:
                conf.update(json.load(f))
        except (OSError, ValueError):
            pass
    return conf


def servers():
    """Frappe web servers running on this machine: [{"port", "site" (None = every site, chosen by Host)}]."""
    found = {}
    for cmdline in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(cmdline, "rb") as f:
                args = f.read().decode(errors="replace").split("\0")
        except OSError:
            continue
        if "serve" not in args or not any(a.endswith("bench_helper") or a == "frappe" for a in args):
            continue

        def opt(name):
            i = args.index(name) + 1 if name in args else 0
            return args[i] if 0 < i < len(args) else None

        port = opt("--port")
        if port and port.isdigit():
            # the reloader runs each server twice (parent and child): one entry per port and site
            found[(int(port), opt("--site") or "")] = {"port": int(port), "site": opt("--site")}
    return sorted(found.values(), key=lambda s: s["port"])


def _ping(url, host=None):
    import requests

    try:
        r = requests.get(url, headers={"Host": host} if host else {}, timeout=PING_TIMEOUT, allow_redirects=False)
        return r.status_code == 200 and r.json().get("message") == "pong"
    except Exception:
        return False


def served_at(site, primary_domain=None):
    """Where the site answers: local ports (development) and its public address (production)."""
    out = []
    for server in servers():
        if server["site"] not in (None, site):
            continue  # that server is pinned to another site
        if _ping(f"http://127.0.0.1:{server['port']}/api/method/ping", host=site):
            out.append({"url": f"http://{site}:{server['port']}",
                        "via": f"port {server['port']}" + ("" if server["site"] else ", which serves every site by name")})
    if not site.endswith(".localhost"):
        for host in dict.fromkeys(filter(None, (primary_domain, site))):
            if _ping(f"https://{host}/api/method/ping"):
                out.append({"url": f"https://{host}", "via": "its public address"})
    return out


def _database(conf):
    """Size, tables and use of the site's database, read with the site's own login."""
    import MySQLdb

    name = conf.get("db_name")
    out = {"name": name, "type": conf.get("db_type") or "mariadb"}
    if out["type"] != "mariadb" or not name:
        return out
    try:
        conn = MySQLdb.connect(host=conf.get("db_host") or "127.0.0.1", port=int(conf.get("db_port") or 3306),
                               user=conf.get("db_user") or name, passwd=conf.get("db_password") or "", db=name,
                               connect_timeout=5)
    except Exception as e:
        out["error"] = "The site's database login was refused" if "1045" in str(e) else "The database could not be reached"
        return out
    try:
        cur = conn.cursor()

        def q(sql, *args):
            cur.execute(sql, args)
            return cur.fetchall()

        tables, size = q("SELECT COUNT(*), COALESCE(SUM(data_length + index_length), 0) FROM information_schema.tables "
                         "WHERE table_schema = %s", name)[0]
        out.update({"tables": int(tables), "size_mb": round(flt(size) / 1048576, 1)})
        have = {r[0] for r in q("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", name)}
        if "tabUser" in have:
            users, last_login = q("SELECT COUNT(*), MAX(last_login) FROM `tabUser` WHERE enabled = 1 "
                                  "AND name NOT IN ('Administrator', 'Guest')")[0]
            out.update({"users": int(users), "last_login": str(last_login) if last_login else None})
        if "tabStudent" in have:
            out["students"] = int(q("SELECT COUNT(*) FROM `tabStudent`")[0][0])
        if "tabInstalled Application" in have:
            out["apps"] = [{"app": a, "version": v, "branch": b} for a, v, b in q(
                "SELECT app_name, app_version, git_branch FROM `tabInstalled Application` ORDER BY idx")]
    finally:
        conn.close()
    return out


def _last_backup(site):
    files = glob.glob(os.path.join(_site_dir(site), "private", "backups", "*-database.sql.gz"))
    if not files:
        return None
    newest = max(files, key=os.path.getmtime)
    return {"file": os.path.basename(newest), "size_mb": round(os.path.getsize(newest) / 1048576, 1),
            "on": frappe.utils.convert_utc_to_system_timezone(datetime.datetime.fromtimestamp(
                os.path.getmtime(newest), datetime.timezone.utc).replace(tzinfo=None)).strftime("%Y-%m-%d %H:%M")}


# ----------------------------------------------------------------------------- operations run from the dialog
# The only commands that can be run from the browser, each with its time limit. Nothing else, and no arguments.
ACTIONS = {
    "Backup": (("backup", "--with-files"), 30 * 60),
    "Migrate": (("migrate",), 60 * 60),
    "Clear Cache": (("clear-cache",), 5 * 60),
}


def _operable_site(doc):
    """The school's site, if this control plane may run commands on it here; otherwise refuse."""
    from stemic_control.onboarding import environment_problem

    site = doc.canonical_site
    if not site or not SITE_NAME.fullmatch(site):
        frappe.throw("This school has no site yet", frappe.ValidationError)
    if not os.path.isdir(_site_dir(site)):
        frappe.throw(f"{site} is not on this bench, so it cannot be run from here", frappe.ValidationError)
    problem = environment_problem()
    if problem:
        frappe.throw(f"This bench is not authorised to run commands on school sites: {problem}", frappe.ValidationError)
    return site


def _active_operation(site):
    """An operation still queued or running on this site (a locking read); one left Running by a worker that died
    stops counting once it is well past the longest time limit."""
    stale = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=-(max(t for _a, t in ACTIONS.values()) + 600))
    rows = frappe.db.sql("SELECT name, action FROM `tabSaaS Site Operation` WHERE site = %s AND status IN ('Queued', 'Running') "
                         "AND creation > %s LIMIT 1 FOR UPDATE", (site, stale), as_dict=True)
    return rows[0] if rows else None


@frappe.whitelist(methods=["POST"])
def run_operation(tenant, action):
    """Back up, migrate or clear the cache of a school's site, in a background worker (platform admins only)."""
    from stemic_control.api import _admin

    _admin()
    if action not in ACTIONS:
        frappe.throw("Choose Backup, Migrate or Clear Cache", frappe.ValidationError)
    frappe.db.sql("SELECT name FROM `tabSaaS Tenant` WHERE name = %s FOR UPDATE", (tenant,))  # one request at a time
    doc = frappe.get_doc("SaaS Tenant", tenant)
    doc.check_permission("write")
    site = _operable_site(doc)
    busy = _active_operation(site)
    if busy:
        frappe.throw(f"{busy.action} ({busy.name}) is still running on {site}; wait for it to finish", frappe.ValidationError)
    op = frappe.get_doc({"doctype": "SaaS Site Operation", "tenant": tenant, "site": site, "action": action,
                         "status": "Queued", "requested_by": frappe.session.user})
    op.flags.site_operation_service = True
    op.insert(ignore_permissions=True)
    frappe.enqueue("stemic_control.site_runtime.perform_operation", queue="long", timeout=ACTIONS[action][1] + 120,
                   operation=op.name, enqueue_after_commit=True, job_id=f"stemic-site-op-{op.name}", deduplicate=True)
    return {"operation": op.name, "status": "Queued"}


def _summary(action, output):
    if action == "Backup":
        found = [line.strip() for line in output.splitlines() if line.strip().startswith(("Database", "Config", "Public", "Private"))]
        return "; ".join(found)[:500] or "Backup taken"
    return {"Migrate": "Migrated", "Clear Cache": "Cache cleared"}[action]


def _set(op, values):
    frappe.db.set_value("SaaS Site Operation", op, values, update_modified=True)
    frappe.db.commit()


def perform_operation(operation):
    """Background worker: run the one allowed command and record what happened."""
    from stemic_control import provisioner

    rows = frappe.db.sql("SELECT action, site, status FROM `tabSaaS Site Operation` WHERE name = %s FOR UPDATE",
                         (operation,), as_dict=True)
    if not rows or rows[0].status != "Queued":
        return rows[0].status if rows else "missing"
    action, site = rows[0].action, rows[0].site
    _set(operation, {"status": "Running", "started_on": frappe.utils.now_datetime()})
    args, timeout = ACTIONS[action]
    secrets = tuple(filter(None, (_config(site).get("db_password"), frappe.conf.get("stemic_db_root_password"))))
    try:
        output = provisioner._frappe_cli("--site", site, *args, timeout=timeout, secrets_=secrets)
    except Exception as e:
        message = str(e) if isinstance(e, provisioner.ProvisioningError) else frappe.get_traceback()
        for secret in secrets:
            message = message.replace(secret, "********")
        _set(operation, {"status": "Failed", "finished_on": frappe.utils.now_datetime(), "summary": message.splitlines()[0][:500]
                         if message else "Failed", "output": message[-20000:]})
        return "Failed"
    _set(operation, {"status": "Succeeded", "finished_on": frappe.utils.now_datetime(), "summary": _summary(action, output),
                     "output": output[-20000:]})
    return "Succeeded"


@frappe.whitelist(methods=["GET"])
def recent_operations(tenant):
    from stemic_control.api import _admin

    _admin()
    frappe.get_doc("SaaS Tenant", tenant).check_permission("read")
    return frappe.get_all("SaaS Site Operation", filters={"tenant": tenant},
                          fields=["name", "action", "status", "requested_by", "creation", "finished_on", "summary"],
                          order_by="creation desc", limit=5)


@frappe.whitelist(methods=["GET"])
def site_status(tenant):
    """Everything the Open Site dialog shows (platform admins only). Never returns a password."""
    from stemic_control.api import _admin

    _admin()
    doc = frappe.get_doc("SaaS Tenant", tenant)
    doc.check_permission("read")
    site = doc.canonical_site
    if not site:
        frappe.throw("This school has no site yet", frappe.ValidationError)
    if not SITE_NAME.fullmatch(site):
        frappe.throw("The school's site name is not a valid host name", frappe.ValidationError)
    if not os.path.isdir(_site_dir(site)):
        return {"site": site, "on_this_bench": False, "served_at": served_at(site, doc.primary_domain)}
    conf = _config(site)
    return {
        "site": site, "on_this_bench": True, "folder": _site_dir(site),
        "bench": os.path.dirname(os.path.dirname(_site_dir(site))),
        "served_at": served_at(site, doc.primary_domain),
        "servers": servers(),
        "database": _database(conf),
        "scheduler": "paused" if conf.get("pause_scheduler") else "on",
        "maintenance_mode": bool(conf.get("maintenance_mode")),
        "installed_apps": conf.get("installed_apps") or [],
        "last_backup": _last_backup(site),
    }
