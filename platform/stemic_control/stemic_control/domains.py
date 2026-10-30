"""A school's own domain, from verified to serving the school (verification itself is api.verify_domain).

1. **Route.** Every verified custom domain of a school with a site is written to `<bench>/config/stemic-domains.json`
   ({hostname: site}). On the server, `stemic-domains-sync` (root, server/README.md) turns that file into nginx config:
   the hostname is sent to the school's site, served with whichever certificate in /etc/ssl/cloudflare covers it. It
   reports what it did in /var/lib/stemic/domains-status.json.
2. **Check.** A random file is put in the school site's public files and fetched over https://<domain>/: the domain
   is live only when that exact file comes back, i.e. DNS, Cloudflare, the certificate and the route all work and
   lead to this school (not merely to some site).
3. **Activate**, then optionally **make primary**: the school's emails and links (site host_name, welcome, license
   emails) then use the domain instead of <slug>.<platform domain>, which keeps working.
"""

import json
import os
import secrets

import frappe
from frappe.utils import now_datetime

from stemic_control import config, provisioner

STATUS_FILE = "/var/lib/stemic/domains-status.json"
SERVING = ("Verified", "Active")  # routed; only Active ones are used in links
PROBLEMS = {
    "no_certificate": "No certificate on the server covers {host}. Create a Cloudflare Origin Certificate for its "
                      "zone and save it as /etc/ssl/cloudflare/<name>.pem and <name>.key (server/README.md).",
    "bad_site": "The server refused the route: the school's site folder was not found.",
    "nginx_failed": "nginx rejected the new configuration; the server kept the previous one. See the sync log "
                    "(journalctl -u stemic-domains).",
}


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


# ----------------------------------------------------------------------------- 1. route
def routes_file() -> str:
    return config.get("stemic_domains_file") or os.path.join(provisioner._bench(), "config", "stemic-domains.json")


def routes() -> dict:
    """{hostname: site} for every verified custom domain of a school that has a site."""
    rows = frappe.db.sql("""SELECT d.hostname, t.canonical_site FROM `tabSaaS Domain` d
        JOIN `tabSaaS Tenant` t ON t.name = d.tenant
        WHERE d.domain_type = 'Custom Domain' AND d.status IN %(serving)s AND IFNULL(t.canonical_site, '') != ''
        ORDER BY d.hostname""", {"serving": SERVING}, as_dict=True)
    return {r.hostname: r.canonical_site for r in rows}


def publish():
    """Write the routes for the server's sync (atomically: it watches the file). Only rewritten when they change."""
    path, data = routes_file(), routes()
    if frappe.flags.in_test and not config.get("stemic_domains_file"):
        return data  # a test must not change the routes the real server serves
    try:
        with open(path) as f:
            if json.load(f).get("domains") == data:
                return data
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{secrets.token_hex(4)}.tmp"
    with open(tmp, "w") as f:
        json.dump({"domains": data, "written_on": str(now_datetime())}, f, indent=1, sort_keys=True)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return data


def server_status() -> dict:
    """What the server's sync last did ({} where it is not installed, e.g. development)."""
    try:
        with open(config.get("stemic_domains_status_file") or STATUS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# ----------------------------------------------------------------------------- 2. check
def _get(url):
    import requests

    return requests.get(url, timeout=15, allow_redirects=False, headers={"Cache-Control": "no-cache"})


def check(hostname) -> dict:
    """Is https://<hostname>/ this school's site? {"ok": bool, "problem": what to fix, in words}."""
    doc = frappe.get_doc("SaaS Domain", hostname)
    site = frappe.db.get_value("SaaS Tenant", doc.tenant, "canonical_site")
    if not site:
        return {"ok": False, "problem": "The school has no site yet: the domain is set up once its site is created."}
    if doc.status not in SERVING:
        return {"ok": False, "problem": f"A {doc.status} domain is not served."}
    files = os.path.join(provisioner._bench(), "sites", site, "public", "files")
    if not os.path.isdir(files):
        return {"ok": False, "problem": f"The school's site {site} is not on this server."}
    name = f"stemic-domain-check-{secrets.token_hex(12)}.txt"
    token = secrets.token_urlsafe(24)
    path = os.path.join(files, name)
    with open(path, "w") as f:
        f.write(token)
    try:
        r = _get(f"https://{hostname}/files/{name}")
    except Exception as e:
        return {"ok": False, "problem": _unreachable(hostname, e)}
    finally:
        os.path.exists(path) and os.remove(path)
    if r.status_code == 200 and r.text.strip() == token:
        return {"ok": True, "problem": None}
    return {"ok": False, "problem": _wrong(hostname, r.status_code)}


def _sync_problem(hostname):
    entry = (server_status().get("domains") or {}).get(hostname)
    if entry and entry.get("problem") in PROBLEMS:
        return PROBLEMS[entry["problem"]].format(host=hostname)
    return None


def _unreachable(hostname, error):
    import socket

    try:
        socket.getaddrinfo(hostname, 443)
    except OSError:
        return (f"{hostname} does not resolve. In its DNS add a CNAME {hostname} -> {_platform()} (Proxied, the orange "
                "cloud, if the zone is on Cloudflare).")
    return f"https://{hostname} could not be reached ({type(error).__name__})." + (
        f" {_sync_problem(hostname)}" if _sync_problem(hostname) else "")


def _wrong(hostname, code):
    sync = _sync_problem(hostname)
    if code == 526:
        return sync or PROBLEMS["no_certificate"].format(host=hostname)
    if code in (521, 522, 523, 525):
        return f"Cloudflare could not connect to the server (error {code}). " + (sync or "Is nginx running?")
    if code in (404, 444):
        if sync:
            return sync
        if not server_status():
            return ("The server is not routing custom domains yet: install stemic-domains-sync (server/README.md), "
                    "then check again.")
        return "The server has not picked up this domain yet (the sync runs when the routes change): check again shortly."
    if code in (301, 302, 307, 308):
        return f"https://{hostname} redirects elsewhere (HTTP {code}): turn off redirect rules for it in its DNS provider."
    return f"https://{hostname} answered HTTP {code}, not this school's site. " + (sync or "")


def _platform():
    from stemic_control.api import platform_domain

    return platform_domain()


# ----------------------------------------------------------------------------- 3. operator actions
def _custom(hostname):
    _admin()
    doc = frappe.get_doc("SaaS Domain", hostname)
    doc.check_permission("write")
    if doc.domain_type != "Custom Domain":
        frappe.throw("The school's own subdomain is managed by provisioning", frappe.ValidationError)
    return doc


@frappe.whitelist(methods=["POST"])
def activate(domain):
    """Verified -> Active once the domain really serves this school."""
    doc = _custom(domain)
    if doc.status == "Active":
        return {"domain": doc.name, "status": doc.status}
    if doc.status != "Verified":
        frappe.throw("Verify the domain's DNS record first", frappe.ValidationError)
    publish()
    result = check(doc.name)
    if not result["ok"]:
        frappe.throw(result["problem"], frappe.ValidationError, title="Not live yet")
    doc.db_set("status", "Active")
    return {"domain": doc.name, "status": "Active"}


@frappe.whitelist(methods=["GET"])
def status(domain):
    """For the domain form: the server's sync result and, on request, a live check."""
    doc = _custom(domain)
    return {"routed": doc.hostname in routes(), "server": (server_status().get("domains") or {}).get(doc.hostname),
            "sync_installed": bool(server_status()), "platform_domain": _platform(),
            "primary": frappe.db.get_value("SaaS Tenant", doc.tenant, "primary_domain") == doc.hostname}


@frappe.whitelist(methods=["POST"])
def make_primary(domain):
    """The school's links and emails use this domain from now on."""
    doc = _custom(domain)
    if doc.status != "Active":
        frappe.throw("Only an active domain can be the school's main address", frappe.ValidationError)
    _set_primary(doc.tenant, doc.hostname)
    return {"domain": doc.name, "primary": True}


@frappe.whitelist(methods=["POST"])
def disable(domain):
    """Stop serving the domain; if it was the school's main address, the school's own subdomain takes over."""
    doc = _custom(domain)
    if doc.status == "Disabled":
        return {"domain": doc.name, "status": doc.status}
    doc.db_set({"status": "Disabled", "is_primary": 0})
    if frappe.db.get_value("SaaS Tenant", doc.tenant, "primary_domain") == doc.hostname:
        _set_primary(doc.tenant, None)
    publish()
    return {"domain": doc.name, "status": "Disabled"}


def _set_primary(tenant, hostname):
    """hostname None: back to the school's site address."""
    site = frappe.db.get_value("SaaS Tenant", tenant, "canonical_site")
    host = hostname or site
    if site:
        provisioner.set_public_url(site, host)
    frappe.db.set_value("SaaS Tenant", tenant, "primary_domain", host)
    for name in frappe.get_all("SaaS Domain", filters={"tenant": tenant}, pluck="name"):
        frappe.db.set_value("SaaS Domain", name, "is_primary", int(name == host))


def public_host(tenant) -> str | None:
    """Where people should go: the school's main custom domain once it is live, else its site."""
    t = frappe.db.get_value("SaaS Tenant", tenant, ["primary_domain", "canonical_site"], as_dict=True) or {}
    primary = t.get("primary_domain")
    if primary and frappe.db.get_value("SaaS Domain", primary, ["domain_type", "status"]) == ("Custom Domain", "Active"):
        return primary
    return t.get("canonical_site")


# ----------------------------------------------------------------------------- scheduler
def hourly():
    """Keep the routes current and activate verified domains as soon as they serve their school."""
    publish()
    for name in frappe.get_all("SaaS Domain", filters={"domain_type": "Custom Domain", "status": "Verified"}, pluck="name"):
        try:
            if check(name)["ok"]:
                frappe.db.set_value("SaaS Domain", name, "status", "Active")
                frappe.db.commit()
                from stemic_control.alerts import notify_admins

                notify_admins(f"{name} is live", "The domain now serves its school. Use Make Primary on the domain if "
                              "the school's emails and links should use it.", "SaaS Domain", name)
        except Exception:
            frappe.log_error(title=f"Checking custom domain {name} failed")
