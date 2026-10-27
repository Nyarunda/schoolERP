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
    sites = os.path.dirname(_site_dir(site))
    conf = {}
    for path in (os.path.join(sites, "common_site_config.json"), os.path.join(sites, site, "site_config.json")):
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
