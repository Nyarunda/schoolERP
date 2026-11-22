"""Stemic expenses: the default categories and their accounts, once an accounting company is set."""

import frappe


def execute():
    frappe.reload_doc("stemic_control", "doctype", "stemic_expense_category")
    frappe.reload_doc("stemic_control", "doctype", "stemic_expense")
    from stemic_control import accounting, expenses

    if accounting.enabled():
        try:
            expenses.ensure_categories(accounting.company())
        except Exception:
            frappe.log_error(title="Stemic expense categories not created")
