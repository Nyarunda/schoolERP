"""Signed School ERP license keys, issued from a subscription.

The key format is School ERP's: base64url(payload_json) + "." + base64url(ed25519_signature), with the payload
JSON sorted and compact. School ERP verifies it with the vendor public key it ships with, so this site needs the
matching private key, which never leaves the control plane:

    stemic_license_private_key_file   path to a file holding the base64url private key (from license_tool.py keygen)
"""

import base64
import json

import frappe
from frappe.utils import getdate, nowdate

from stemic_control import config, policy


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict, private_key_b64: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    unknown = set(payload.get("modules", [])) - set(policy.MODULES)
    if unknown:
        raise ValueError(f"Unknown modules: {', '.join(sorted(unknown))}")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{_b64e(body)}.{_b64e(Ed25519PrivateKey.from_private_bytes(_b64d(private_key_b64)).sign(body))}"


def decode(key: str) -> dict | None:
    """The payload of a key, unverified (for display only); None if it is not one."""
    try:
        return json.loads(_b64d(key.split(".", 1)[0]))
    except Exception:
        return None


def can_sign() -> bool:
    return bool(config.secret("stemic_license_private_key_file")[0])


def _private_key() -> str:
    path = config.secret("stemic_license_private_key_file")[0]
    if not path:
        frappe.throw("License signing is not set up: put the vendor private key in a file and set "
                     "stemic_license_private_key_file in this site's site_config.json", frappe.ValidationError)
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        frappe.throw("Cannot read the license private key file set in stemic_license_private_key_file", frappe.ValidationError)


def plan_modules(plan) -> list[str]:
    raw = frappe.db.get_value("SaaS Plan", plan, "modules") or "[]"
    try:
        modules = json.loads(raw)
    except ValueError:
        modules = []
    return [m for m in modules if m in policy.MODULES]


def issue(subscription: str) -> str:
    """Sign a key for the subscription's school and record it; earlier issued keys of that school are revoked."""
    sub = frappe.get_doc("SaaS Subscription", subscription)
    if sub.status not in policy.LICENSABLE:
        frappe.throw(f"A {sub.status} subscription cannot be licensed", frappe.ValidationError)
    if sub.ends_on and getdate(sub.ends_on) < getdate(nowdate()):
        frappe.throw("This subscription has ended. Renew it before issuing a license.", frappe.ValidationError)
    tenant = frappe.get_doc("SaaS Tenant", sub.tenant)
    if not tenant.canonical_site:
        frappe.throw("The school has no site yet. Provision it first; the key is tied to the site name.", frappe.ValidationError)

    plan = frappe.get_doc("SaaS Plan", sub.plan)
    modules = plan_modules(plan.name)
    issued = nowdate()
    payload = {"school": tenant.school_name, "modules": modules, "issued": issued,
               "max_students": int(plan.student_limit or 0), "site": tenant.canonical_site}
    if sub.ends_on:
        payload["expires"] = str(sub.ends_on)
    key = sign(payload, _private_key())

    for old in frappe.get_all("SaaS License", filters={"tenant": tenant.name, "status": "Issued"}, pluck="name"):
        frappe.db.set_value("SaaS License", old, "status", "Revoked")
    lic = frappe.get_doc({
        "doctype": "SaaS License", "tenant": tenant.name, "subscription": sub.name, "plan": plan.name,
        "site": tenant.canonical_site, "issued_on": issued, "expires_on": sub.ends_on,
        "max_students": payload["max_students"], "modules": "\n".join(policy.MODULES[m] for m in modules) or "Core only",
    })
    lic.signed_key = key
    lic.status = "Issued"
    lic.flags.from_issue = True
    lic.insert()
    from stemic_control import communications

    communications.queue("License Issued", license=lic.name)
    return lic.name


def _setting(field) -> bool:
    value = frappe.get_cached_doc("Stemic Settings").get(field)
    return value is None or bool(int(value or 0))  # not saved yet counts as on (patches.default_onboarding_settings)


def auto_issue(subscription: str, why: str = "ready"):
    """Issue the school's key without an operator: when its site is ready (why="ready") or a payment extended its
    subscription (why="renewal"). Never fails the caller: if it cannot be issued, the platform admins are told why.
    Returns the license name, or None with the reason it was not issued."""
    switch = "auto_issue_license" if why == "ready" else "auto_renew_license"
    if not _setting(switch):
        return None, "switched off in Stemic Settings > Onboarding"
    sub = frappe.db.get_value("SaaS Subscription", subscription, ["name", "tenant", "status", "ends_on"], as_dict=True)
    if not sub:
        return None, "no subscription"
    site = frappe.db.get_value("SaaS Tenant", sub.tenant, "canonical_site")
    if not site:
        return None, "the school has no site yet"  # issued when the site is ready
    if sub.status not in policy.LICENSABLE or (sub.ends_on and getdate(sub.ends_on) < getdate(nowdate())):
        return None, f"a {sub.status} subscription is not licensed"
    if why == "renewal":
        # only when the key in force would stop before the new end date
        current = frappe.db.get_value("SaaS License", {"tenant": sub.tenant, "status": "Issued"}, "expires_on",
                                      order_by="creation desc")
        if current and sub.ends_on and getdate(current) >= getdate(sub.ends_on):
            return None, "the key in force already covers the subscription"
    if not can_sign():
        _tell(sub.tenant, why, "License signing is not set up on this Control Center (stemic_license_private_key_file).")
        return None, "license signing is not set up"
    try:
        frappe.db.savepoint("auto_license")
        name = issue(subscription)
    except Exception as e:
        frappe.db.rollback(save_point="auto_license")
        frappe.clear_messages()
        frappe.log_error(title=f"Automatic license not issued for {sub.tenant}")
        _tell(sub.tenant, why, str(e).splitlines()[0][:300] if str(e) else e.__class__.__name__)
        return None, str(e)
    frappe.get_doc("SaaS Tenant", sub.tenant).add_comment(
        "Info", f"License {name} issued automatically ({'site ready' if why == 'ready' else 'subscription renewed'}).")
    return name, None


def _tell(tenant, why, reason):
    from stemic_control.alerts import notify_admins

    what = "its site is ready" if why == "ready" else "it renewed"
    notify_admins(f"No license key was issued for {tenant}",
                  f"{frappe.utils.escape_html(reason)}<br>The school needs a key now that {what}: open its subscription and "
                  "use Issue License.", "SaaS Tenant", tenant)


def current_subscription(tenant):
    """The school's subscription in force: the one on the school, else its newest one that is not cancelled."""
    sub = frappe.db.get_value("SaaS Tenant", tenant, "subscription")
    if sub and frappe.db.get_value("SaaS Subscription", sub, "status") != "Cancelled":
        return sub
    return frappe.db.get_value("SaaS Subscription", {"tenant": tenant, "status": ("!=", "Cancelled")}, "name",
                               order_by="creation desc")


def after_site_ready(tenant):
    """Called once a school's site exists (built or linked): its key, from its plan, without an operator."""
    sub = current_subscription(tenant)
    return auto_issue(sub, "ready") if sub else (None, "no subscription")


def auto_issue_job(subscription, why="renewal"):
    """Background job (after a payment commits)."""
    result = auto_issue(subscription, why)
    frappe.db.commit()
    return result
