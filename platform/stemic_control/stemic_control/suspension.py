"""Suspending a school stops its site; resuming starts it again.

On the school's site (this bench): `stemic_suspended` makes every request answer "service suspended"
(school_erp.suspension.check) and `pause_scheduler` stops its scheduled jobs (billing, SMS, reminders). Resume
clears both. The Control Center only records the new status once the site has really changed.
"""

import frappe

from stemic_control import provisioner, site_runtime


def _support_email():
    from stemic_control.communications import brand

    return brand().email


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


def apply(tenant, suspend):
    """Make the school's site match: suspended (blocked, scheduler paused) or running. Returns the site, if any."""
    site = site_of(tenant)
    if not site:
        return None
    school = frappe.db.get_value("SaaS Tenant", tenant, "school_name") or tenant
    if suspend:
        from stemic_control.communications import brand

        name = brand().name
        _set(site, "stemic_suspended_message", f"{school}'s {name} service is suspended. Contact {name} to restore it.")
        _set(site, "stemic_support_email", _support_email())
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
