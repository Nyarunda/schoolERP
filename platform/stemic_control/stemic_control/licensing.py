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

from stemic_control import policy


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
    return bool(frappe.conf.get("stemic_license_private_key_file"))


def _private_key() -> str:
    path = frappe.conf.get("stemic_license_private_key_file")
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
    return lic.name
