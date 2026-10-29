"""Suspending a school stops its site; resuming starts it again.

On the school's site (this bench): `stemic_suspended` makes every request answer "service suspended"
(school_erp.suspension.check) and `pause_scheduler` stops its scheduled jobs (billing, SMS, reminders). Resume
clears both. The Control Center only records the new status once the site has really changed.
"""

import frappe

from stemic_control import provisioner, site_runtime


def _set(site, key, value, parse=False):
    provisioner._frappe_cli("--site", site, "set-config", *(["-p"] if parse else []), key, value, timeout=120)


def site_of(tenant):
    """The school's site on this bench, or None when it has none (yet). A site elsewhere cannot be switched here."""
    site = frappe.db.get_value("SaaS Tenant", tenant, "canonical_site")
    if not site:
        return None
    if not provisioner._site_dir_exists(site):
        frappe.throw(f"{site} is not on this server, so it cannot be suspended or resumed from here", frappe.ValidationError)
    return site


def details(tenant, reason=None):
    """What the suspended page shows: the school, why, what is owed and how to pay, and how to reach Stemic.
    Plain strings only (stored in the site's site_config.json)."""
    from frappe.utils import formatdate, nowdate

    from stemic_control.billing import OPEN
    from stemic_control.communications import _instructions, _money, brand

    b = brand()
    school = frappe.db.get_value("SaaS Tenant", tenant, "school_name") or tenant
    out = {"school": school, "brand": b.name, "color": b.color, "accent": b.accent, "email": b.email, "phone": b.phone,
           "reason": (reason or "").strip()[:300], "since": formatdate(nowdate())}
    owed = frappe.get_all("SaaS Invoice", filters={"tenant": tenant, "docstatus": 1, "status": ("in", OPEN)},
                          fields=["name", "outstanding", "currency", "due_date"], order_by="due_date asc", limit=1)
    if owed:
        inv = owed[0]
        out.update(invoice=inv.name, amount_due=_money(inv.outstanding, inv.currency), due_date=formatdate(inv.due_date),
                   how_to_pay=_instructions(inv.name))
    else:
        out["how_to_pay"] = ""
    return {k: str(v or "") for k, v in out.items()}


def apply(tenant, suspend, reason=None):
    """Make the school's site match: suspended (blocked, scheduler paused) or running. Returns the site, if any."""
    site = site_of(tenant)
    if not site:
        return None
    if suspend:
        info = details(tenant, reason)
        _set(site, "stemic_suspension", repr(info), parse=True)  # what the page shows
        _set(site, "stemic_suspended_message",
             f"{info['school']}'s {info['brand']} service is suspended. Contact {info['brand']} to restore it.")
        _set(site, "stemic_support_email", info["email"])
        _set(site, "pause_scheduler", "1", parse=True)
        _set(site, "stemic_suspended", "1", parse=True)  # last: the block starts once everything else is in place
    else:
        _set(site, "stemic_suspended", "0", parse=True)  # first: the school is back as soon as possible
        _set(site, "pause_scheduler", "0", parse=True)
    conf = site_runtime._config(site)
    if bool(conf.get("stemic_suspended")) != bool(suspend):
        frappe.throw(f"{site} did not take the change: stemic_suspended is {conf.get('stemic_suspended')!r}", frappe.ValidationError)
    return site


def is_blocked(tenant):
    """Whether the school's site is blocked right now (for the school's form)."""
    site = frappe.db.get_value("SaaS Tenant", tenant, "canonical_site")
    if not site or not provisioner._site_dir_exists(site):
        return None
    return bool(site_runtime._config(site).get("stemic_suspended"))
