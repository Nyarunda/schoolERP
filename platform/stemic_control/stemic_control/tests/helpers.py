"""Shared fixtures for tests that need a school the provisioner would accept (not a test module itself)."""

import frappe
from frappe.utils import add_days, nowdate

from stemic_control import onboarding


def plan():
    name = "Onboarding Test Plan"
    if not frappe.db.exists("SaaS Plan", name):
        frappe.get_doc({"doctype": "SaaS Plan", "plan_name": name, "enabled": 1, "monthly_price": 1000, "modules": "[]"}).insert()
    return name


def subscription(tenant, **values):
    agent = frappe.db.get_value("SaaS Tenant", tenant, "agent")
    return frappe.get_doc({"doctype": "SaaS Subscription", "tenant": tenant, "plan": plan(), "agent": agent,
                           "starts_on": nowdate(), "ends_on": add_days(nowdate(), 30), **values}).insert().name


def approve(tenant):
    onboarding.submit_for_approval(tenant)
    onboarding.approve_tenant(tenant, "Checked by the test")


def make_eligible(tenant):
    """Approved, with an approved internal subscription: what queue_provisioning and the provisioner require."""
    approve(tenant)
    sub = subscription(tenant)
    onboarding.grant_billing_exception(sub, onboarding.INTERNAL, "Internal test school")
    return sub


def remove_school(slug):
    """provisioner.run commits, so a test's school would outlive it (and a real scheduler could act on it)."""
    frappe.db.rollback()
    subs = frappe.get_all("SaaS Subscription", filters={"tenant": slug}, pluck="name") or [""]
    invoices = frappe.get_all("SaaS Invoice", filters={"tenant": slug}, pluck="name") or [""]
    for dt, filters in (("SaaS Commission", {"tenant": slug}), ("SaaS Payment", {"invoice": ("in", invoices)}),
                        ("SaaS Invoice", {"name": ("in", invoices)}), ("SaaS Provisioning Job", {"tenant": slug}),
                        ("SaaS Domain", {"tenant": slug}), ("SaaS Subscription", {"name": ("in", subs)}),
                        ("SaaS Tenant", {"name": slug})):
        frappe.db.delete(dt, filters)
    frappe.db.commit()
