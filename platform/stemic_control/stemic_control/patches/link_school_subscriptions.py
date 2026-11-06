"""Point each school at its live subscription (SaaS Tenant.subscription). Nothing set it before, so a school's form
said "Subscription: None yet" and the dashboards could not join schools to their plans."""

import frappe


def execute():
    for tenant in frappe.get_all("SaaS Tenant", filters={"subscription": ("in", ["", None])}, pluck="name"):
        sub = frappe.db.get_value("SaaS Subscription", {"tenant": tenant, "status": ("!=", "Cancelled")}, "name",
                                  order_by="creation desc")
        if sub:
            frappe.db.set_value("SaaS Tenant", tenant, "subscription", sub, update_modified=False)
