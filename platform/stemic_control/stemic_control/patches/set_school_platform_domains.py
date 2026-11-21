"""Pin every existing school to the domain its address is on today (SaaS Tenant.platform_domain), so adding or
changing the default platform domain later never moves anyone."""

import frappe


def execute():
    from stemic_control.api import known_domains, platform_domain

    default = platform_domain()
    bases = known_domains()
    for t in frappe.get_all("SaaS Tenant", filters={"platform_domain": ("in", ["", None])}, fields=["name", "slug"]):
        own = frappe.get_all("SaaS Domain", filters={"tenant": t.name, "domain_type": "Stemic Subdomain"}, pluck="hostname")
        domain = next((b for b in bases if f"{t.slug}.{b}" in own), default)
        frappe.db.set_value("SaaS Tenant", t.name, "platform_domain", domain, update_modified=False)
