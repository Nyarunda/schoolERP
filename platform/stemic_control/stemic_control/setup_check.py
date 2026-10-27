"""The Setup Check on Stemic Settings: is this control plane ready to provision, license and bill schools?

Every check reports ok (True), needs attention (False) or information (None), with what to do about it. Secrets are
used to test (can the key sign, can the database password log in) but never returned.
"""

import os

import frappe

from stemic_control import config


def _item(area, label, ok, detail, fix=""):
    return {"area": area, "label": label, "ok": ok, "detail": detail, "fix": fix}


def _platform():
    out = []
    source = config.source("stemic_platform_domain")
    out.append(_item("Platform", "Platform domain", source != "default",
                     f"{config.get('stemic_platform_domain')} (from {'the server' if source == 'site_config' else 'these settings' if source == 'settings' else 'the built-in default'})",
                     "Enter your own domain on the Platform tab." if source == "default" else ""))
    return out


def _licensing():
    path = config.secret("stemic_license_private_key_file")[0]
    if not path:
        return [_item("Licensing", "License signing key", False, "Not configured: Issue License will refuse.",
                      "Put the vendor private key in a file on the server and set stemic_license_private_key_file in site_config.json.")]
    try:
        with open(path) as f:
            raw = f.read().strip()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from stemic_control.licensing import _b64d, _b64e

        public = _b64e(Ed25519PrivateKey.from_private_bytes(_b64d(raw)).public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    except OSError:
        return [_item("Licensing", "License signing key", False, "The key file cannot be read by the web server.",
                      "Check the path in stemic_license_private_key_file and the file's permissions.")]
    except Exception:
        return [_item("Licensing", "License signing key", False, "The file does not hold a valid signing key.",
                      "Use the private key printed by license_tool.py keygen.")]
    out = [_item("Licensing", "License signing key", True, "Configured and able to sign.")]
    try:
        from school_erp.licensing.public_key import PUBLIC_KEY
    except ImportError:
        out.append(_item("Licensing", "Matches School ERP", None, "School ERP is not on this server, so its key cannot be compared."))
    else:
        match = PUBLIC_KEY == public
        out.append(_item("Licensing", "Matches School ERP", match,
                         "Keys signed here are accepted by School ERP." if match else "School ERP checks keys against a different public key: schools would reject them.",
                         "" if match else "Use the private key that belongs to school_erp/licensing/public_key.py."))
    return out


def _provisioner():
    from stemic_control import provisioner

    if not provisioner.enabled():
        return [_item("Provisioning", "Create sites on this server", None,
                      "Off: queued schools wait for an external provisioner.", "Switch it on in the Platform tab to create sites here.")]
    out = [_item("Provisioning", "Create sites on this server", True, f"On: sites are named <school>.{config.get('stemic_site_domain')}.")]
    from stemic_control.onboarding import environment_problem

    problem = environment_problem()
    out.append(_item("Provisioning", "Authorised environment", not problem,
                     problem or f"{frappe.conf.get('stemic_provision_environment')}: this bench may build school sites.",
                     "Set stemic_provision_environment and stemic_provision_allowed_benches in site_config.json." if problem else ""))
    bench = provisioner._bench()
    ok = os.path.isfile(os.path.join(bench, "env", "bin", "python"))
    out.append(_item("Provisioning", "Bench", ok, bench, "" if ok else "Set Bench Path to a bench with an env/ folder."))
    missing = [a for a in provisioner._apps() if not os.path.isdir(os.path.join(bench, "apps", a))]
    out.append(_item("Provisioning", "School apps", not missing,
                     ", ".join(provisioner._apps()) + (f" (missing: {', '.join(missing)})" if missing else ""),
                     "Install the missing apps on the bench (bench get-app)." if missing else ""))
    password, where = config.secret("stemic_db_root_password")
    account = provisioner._root_username()
    if not password:
        out.append(_item("Provisioning", "Database access", False, "No password for the account that creates school databases.",
                         "Set STEMIC_DB_ROOT_PASSWORD in the workers' environment (README: Secrets)."))
    else:
        try:
            import MySQLdb

            MySQLdb.connect(host=frappe.conf.db_host or "127.0.0.1", port=int(frappe.conf.db_port or 3306), user=account,
                            passwd=password, connect_timeout=5).close()
            out.append(_item("Provisioning", "Database access", True, f"The {account} account logs in (password from {where.replace('_', ' ')})."))
        except Exception:
            out.append(_item("Provisioning", "Database access", False, f"The {account} account's password does not log in.",
                             "Correct STEMIC_DB_ROOT_PASSWORD (or stemic_db_root_password)."))
        out.append(_item("Provisioning", "Limited database account", account != "root",
                         f"Schools are created as {account}." + ("" if account != "root" else " Root can read and drop every "
                                                                 "database on this server, including other applications'."),
                         "" if account != "root" else "Create the stemic_provisioner account (README: Secrets) and set "
                                                      "STEMIC_DB_ROOT_USERNAME."))
    return out + _secret_sources()


def _secret_sources():
    """Where each secret is read from: the environment (loaded from a protected file) rather than site_config.json."""
    out = []
    production = frappe.conf.get("stemic_provision_environment") == "production"
    for key, variable in config.SECRETS.items():
        value, where = config.secret(key)
        if not value:
            continue
        out.append(_item("Secrets", key.replace("stemic_", "").replace("_", " ").capitalize(),
                         True if where == "environment" else (False if production else None),
                         f"From the environment ({variable})." if where == "environment"
                         else "From site_config.json, which every bench command and backup can read.",
                         "" if where == "environment" else f"Move it to {variable} in a file only the bench's user can read "
                                                           "(README: Secrets)."))
    return out


def _background():
    from frappe.utils.scheduler import is_scheduler_disabled

    out = [_item("Background jobs", "Scheduler", not is_scheduler_disabled(),
                 "Running daily billing and the provisioner check." if not is_scheduler_disabled() else "Disabled: no overdue marking, renewal invoices or provisioning retries.",
                 "" if not is_scheduler_disabled() else "Run: bench --site <admin site> enable-scheduler")]
    try:
        from frappe.utils.background_jobs import get_workers

        workers = len(get_workers())
    except Exception:
        workers = 0
    out.append(_item("Background jobs", "Workers", workers > 0, f"{workers} running" if workers else "None running: sites are not created.",
                     "" if workers else "Start them with bench start (development) or supervisor (production)."))
    return out


def _business():
    out = []
    plans = frappe.get_all("SaaS Plan", filters={"enabled": 1}, fields=["name", "monthly_price", "modules"])
    out.append(_item("Billing", "Plans", bool(plans), ", ".join(p.name for p in plans) or "No enabled plan",
                     "" if plans else "Create a plan under Billing > Plans."))
    s = frappe.get_cached_doc("Stemic Settings")
    out.append(_item("Billing", "Invoice details", bool(s.seller_name and s.payment_instructions),
                     "Seller name and payment instructions set." if s.seller_name and s.payment_instructions else "Invoices would show no seller name or way to pay.",
                     "" if s.seller_name and s.payment_instructions else "Fill in the Billing tab."))
    email = frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1})
    out.append(_item("Billing", "Outgoing email", bool(email), email or "No default outgoing email account.",
                     "" if email else "Add one under Email Account to send invoices and keys."))
    from stemic_control.billing import ledger_mismatches

    wrong = ledger_mismatches(limit=6)
    out.append(_item("Billing", "Invoices match their payments", not wrong,
                     "Every submitted invoice agrees with its payments." if not wrong
                     else "; ".join(f"{m['invoice']}: {m['problem']}" for m in wrong[:5]) + (" …" if len(wrong) > 5 else ""),
                     "" if not wrong else "Open each invoice and its payments; the submitted payments are authoritative."))
    unpaid = frappe.get_all("SaaS Agent", filters={"status": "Active", "commission_rate": ("in", [0, None])}, pluck="agent_name")
    out.append(_item("Commissions", "Agent rates", not unpaid, "Every active agent has a rate." if not unpaid else f"No rate: {', '.join(unpaid)}",
                     "" if not unpaid else "Set a commission rate on each agent."))
    return out


@frappe.whitelist(methods=["GET"])
def status():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)
    items = _platform() + _licensing() + _provisioner() + _background() + _business()
    sources = {key: config.source(key) for key in config.SETTINGS}
    return {"items": items, "ready": all(i["ok"] is not False for i in items), "sources": sources}
