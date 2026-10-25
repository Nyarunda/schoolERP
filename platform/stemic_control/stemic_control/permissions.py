"""Agents see only the schools and subscriptions they brought in, and their own agent record."""

import frappe

PLATFORM_ROLES = {"System Manager", "Stemic Platform Admin"}


def _platform(user) -> bool:
    return user == "Administrator" or bool(PLATFORM_ROLES & set(frappe.get_roles(user)))


def _agent_of(user) -> str | None:
    return frappe.db.get_value("SaaS Agent", {"user": user, "status": "Active"}, "name")


def _agent_condition(table: str, user) -> str:
    user = user or frappe.session.user
    if _platform(user):
        return ""
    agent = _agent_of(user)
    return f"`tab{table}`.agent = {frappe.db.escape(agent)}" if agent else "1=0"


def tenant_query(user=None):
    return _agent_condition("SaaS Tenant", user)


def subscription_query(user=None):
    return _agent_condition("SaaS Subscription", user)


def agent_query(user=None):
    user = user or frappe.session.user
    return "" if _platform(user) else f"`tabSaaS Agent`.user = {frappe.db.escape(user)}"


def _own_rows(doc, ptype, user, matches) -> bool | None:
    user = user or frappe.session.user
    if _platform(user):
        return None  # role permissions decide
    return ptype == "read" and matches(user)


def tenant_has_permission(doc, ptype=None, user=None):
    return _own_rows(doc, ptype, user, lambda u: bool(doc.agent) and doc.agent == _agent_of(u))


def subscription_has_permission(doc, ptype=None, user=None):
    return _own_rows(doc, ptype, user, lambda u: bool(doc.agent) and doc.agent == _agent_of(u))


def agent_has_permission(doc, ptype=None, user=None):
    return _own_rows(doc, ptype, user, lambda u: doc.user == u)
