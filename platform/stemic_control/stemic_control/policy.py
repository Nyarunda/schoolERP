"""Control-plane rules that need no Frappe: identifiers, status transitions, DNS answers."""

import re

SLUG = re.compile(r"^[a-z][a-z0-9-]{2,48}$")
# One or more DNS labels and a TLD: no scheme, port, path, IP literal or empty label
HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
RESERVED = {"admin", "www", "api", "mail", "billing", "agents", "support", "status", "app"}

VERIFICATION_PREFIX = "_stemic-verification."

# Which status may follow which. Anything not listed is refused.
# Draft -> Pending Approval -> Approved -> Pending (site job queued) -> Provisioning -> Active; see onboarding.py
TENANT_TRANSITIONS = {
    "Draft": {"Pending Approval"},
    "Pending Approval": {"Approved", "Rejected", "Draft"},
    "Approved": {"Pending", "Rejected"},
    "Pending": {"Provisioning", "Failed", "Approved", "Draft"},  # a refused job goes back to Approved (or Draft)
    "Provisioning": {"Active", "Failed"},
    "Active": {"Suspended"},
    "Suspended": {"Active"},
    "Failed": {"Pending", "Pending Approval", "Rejected", "Draft"},
    "Rejected": {"Draft"},
}
JOB_TRANSITIONS = {
    "Queued": {"Running", "Failed"},
    "Running": {"Succeeded", "Failed"},
    "Succeeded": set(),
    "Failed": set(),  # retry with a new idempotency key
}
# Subscription billing states an operator may move between (renewing always ends in Active)
SUBSCRIPTION_TRANSITIONS = {
    "Trial": {"Active", "Past Due", "Cancelled"},
    "Active": {"Past Due", "Cancelled"},
    "Past Due": {"Active", "Grace", "Suspended", "Cancelled"},
    "Grace": {"Active", "Suspended", "Cancelled"},
    "Suspended": {"Active", "Cancelled"},
    "Cancelled": set(),
}
# Statuses in which a school may hold a working license key
LICENSABLE = {"Trial", "Active", "Past Due", "Grace"}

# School ERP module codes and labels; must match school_erp.logic.license.MODULES
MODULES = {
    "fees": "Fees, Payments & Statements",
    "timetable": "Timetable",
    "transport": "Transport",
    "lunch": "Lunch",
    "activities": "Games & Activities",
    "messaging": "SMS & Email to Parents",
    "mpesa": "M-Pesa Paybill Auto-posting",
    "staff": "Staff, Leave & Duty Reports",
    "welfare": "Discipline & Complaints",
    "expenses": "Expenses & Approvals",
    "transport_ops": "Driver Daily Logs & Vehicles",
    "exams": "Exams & Report Cards",
    "portal": "Parent Portal & Online Fee Payment",
    "pocket_money": "Pocket Money",
    "boarding": "Boarding & Exeat",
    "homework": "Homework & Assignments",
    "admissions": "Online Admissions",
}

# Tenant status a job moves its tenant to: (action, job status) -> tenant status
JOB_EFFECT = {
    ("Create Site", "Running"): "Provisioning",
    ("Create Site", "Succeeded"): "Active",
    ("Create Site", "Failed"): "Failed",
    ("Suspend", "Succeeded"): "Suspended",
    ("Resume", "Succeeded"): "Active",
}


def can_move(transitions: dict, old: str | None, new: str) -> bool:
    return old == new or new in transitions.get(old or "", set())


def is_hostname(value: str) -> bool:
    return bool(HOST.fullmatch(value or ""))


def subdomain_of(host: str, platform_domain: str) -> bool:
    return host.endswith("." + platform_domain)


def reserved_hosts(platform_domain: str) -> set[str]:
    return {platform_domain} | {f"{name}.{platform_domain}" for name in RESERVED}


def txt_values(doh_answer: dict) -> list[str]:
    """TXT strings from a DNS-over-HTTPS JSON answer (RFC 8484 JSON format used by Cloudflare/Google).

    A TXT record over 255 bytes arrives as several quoted strings; they are joined back together."""
    values = []
    for record in doh_answer.get("Answer") or []:
        if record.get("type") != 16:  # TXT
            continue
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', record.get("data") or "")
        values.append("".join(parts) if parts else (record.get("data") or "").strip('"'))
    return values
