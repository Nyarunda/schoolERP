"""Figures for the Stemic Control workspaces that a Number Card cannot count by itself."""

import frappe


@frappe.whitelist()
def monthly_recurring_revenue(filters=None):
    """Sum of the monthly plan price of every Active subscription."""
    if not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)
    total = frappe.db.sql(
        """select coalesce(sum(p.monthly_price), 0)
        from `tabSaaS Subscription` s join `tabSaaS Plan` p on p.name = s.plan
        where s.status = 'Active'"""
    )[0][0]
    return {"value": total, "fieldtype": "Currency"}
