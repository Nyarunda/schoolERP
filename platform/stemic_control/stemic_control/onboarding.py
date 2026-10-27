"""Who may get a school site. Denied by default: a site is built only for a school an operator approved, that is
commercially eligible, by a provisioner running where the deployment says it may.

Approval        an operator approves the school (Pending Approval -> Approved); only this module writes the approval.
Eligibility     one of the school's subscriptions is
                  - Active with a paid SaaS Invoice,
                  - an approved Free Trial that has not ended, or
                  - an approved Internal / Demo subscription.
                An ordinary unpaid subscription is not enough.
Environment     site_config.json only (never Stemic Settings, a school record or an API argument):
                  stemic_provision_environment       production | staging | development
                  stemic_provision_allowed_benches   bench paths this control plane may build sites in

queue_provisioning checks approval and eligibility so the operator hears about it at once; the provisioner checks all
three again, on locked rows, before it builds anything.
"""

import os

import frappe
from frappe.utils import getdate, now_datetime, nowdate

from stemic_control.policy import TENANT_TRANSITIONS, can_move

ENVIRONMENTS = ("production", "staging", "development")
APPROVAL_FIELDS = ("approved_by", "approved_on", "approval_note")
EXCEPTION_FIELDS = ("billing_exception", "exception_approved_by", "exception_approved_on", "exception_note")
# Statuses a school only reaches after approval (and keeps it in); anything else has no standing approval
APPROVED_STATES = {"Approved", "Pending", "Provisioning", "Active", "Suspended", "Failed"}
FREE_TRIAL, INTERNAL = "Free Trial", "Internal / Demo"


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


def _note(note, what):
    note = (note or "").strip()
    if len(note) < 8:
        frappe.throw(f"Give a reason for the {what} (at least 8 characters)", frappe.ValidationError)
    return note[:500]


def guard_fields(doc, fields):
    """Approval fields are written by this module only (doc.flags.onboarding_service), never from a form or REST."""
    if doc.flags.onboarding_service:
        return
    before = None if doc.is_new() else doc.get_doc_before_save()
    if any((doc.get(f) or None) != ((before.get(f) if before else None) or None) for f in fields):
        frappe.throw("Approvals are recorded through the approval actions, not edited", frappe.PermissionError)


def _save(doc):
    doc.flags.onboarding_service = True
    doc.flags.ignore_permissions = True
    doc.save()


def _lock(doctype, name):
    if not frappe.db.sql(f"SELECT name FROM `tab{doctype}` WHERE name = %s FOR UPDATE", (name,)):
        frappe.throw(f"Unknown {doctype}", frappe.DoesNotExistError)
    return frappe.get_doc(doctype, name)


# ----------------------------------------------------------------------------- the checks
def approved(tenant) -> bool:
    return bool(tenant.approved_on and tenant.approved_by) and tenant.status in APPROVED_STATES


def commercial_basis(tenant_name, lock=False):
    """Why this school may have a site ("Paid subscription", "Free Trial", "Internal / Demo"), or None."""
    rows = frappe.db.sql(
        "SELECT name, status, ends_on, billing_exception, exception_approved_on FROM `tabSaaS Subscription` "
        "WHERE tenant = %s AND status != 'Cancelled' ORDER BY creation DESC" + (" FOR UPDATE" if lock else ""),
        (tenant_name,), as_dict=True)
    for sub in rows:
        granted = bool(sub.exception_approved_on)
        if sub.billing_exception == INTERNAL and granted and sub.status != "Suspended":
            return INTERNAL
        if (sub.billing_exception == FREE_TRIAL and granted and sub.status == "Trial" and sub.ends_on
                and getdate(sub.ends_on) >= getdate(nowdate())):
            return FREE_TRIAL
        if sub.status == "Active" and frappe.db.sql(
                "SELECT name FROM `tabSaaS Invoice` WHERE subscription = %s AND docstatus = 1 AND status = 'Paid' LIMIT 1"
                + (" FOR UPDATE" if lock else ""), (sub.name,)):
            return "Paid subscription"
    return None


def environment_problem():
    """Why this control plane may not build sites here, or None. Read from site_config.json only."""
    from stemic_control import provisioner

    env = frappe.conf.get("stemic_provision_environment")
    if env not in ENVIRONMENTS:
        return f"stemic_provision_environment in site_config.json must be one of {', '.join(ENVIRONMENTS)}"
    allowed = frappe.conf.get("stemic_provision_allowed_benches") or []
    if isinstance(allowed, str):
        allowed = [allowed]
    bench = os.path.realpath(provisioner._bench())
    if bench not in {os.path.realpath(path) for path in allowed if path}:
        return f"Bench {bench} is not in stemic_provision_allowed_benches in site_config.json"
    if env == "production" and (provisioner.site_name("x").endswith(".localhost")):
        return "A production provisioner cannot build .localhost sites: set stemic_site_domain"
    return None


def problems(tenant, lock=False, environment=False) -> list[str]:
    """Everything standing between this school and a site; empty means it may be provisioned."""
    from stemic_control.provisioner import DEMO_NOTE

    out = []
    if tenant.notes == DEMO_NOTE:
        out.append("This is a demo school (sample data): demo schools are never given a site")
    if tenant.status == "Rejected":
        out.append("The school was rejected")
    elif not approved(tenant):
        out.append("The school has not been approved by an operator")
    if not commercial_basis(tenant.name, lock=lock):
        out.append("No paid subscription, approved free trial or approved internal subscription")
    if environment:
        problem = environment_problem()
        if problem:
            out.append(problem)
    return out


# ----------------------------------------------------------------------------- operator actions
@frappe.whitelist(methods=["POST"])
def submit_for_approval(tenant):
    _admin()
    doc = _lock("SaaS Tenant", tenant)
    if doc.status not in ("Draft", "Failed") or (doc.status == "Failed" and approved(doc)):
        frappe.throw(f"A {doc.status} school cannot be sent for approval", frappe.ValidationError)
    doc.status = "Pending Approval"
    _save(doc)
    return {"tenant": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def approve_tenant(tenant, note=None):
    _admin()
    doc = _lock("SaaS Tenant", tenant)
    if doc.status != "Pending Approval":
        frappe.throw("Only a school pending approval can be approved", frappe.ValidationError)
    doc.update({"status": "Approved", "approved_by": frappe.session.user, "approved_on": now_datetime(),
                "approval_note": (note or "").strip()[:500] or None})
    _save(doc)
    return {"tenant": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reject_tenant(tenant, reason):
    _admin()
    reason = _note(reason, "rejection")
    doc = _lock("SaaS Tenant", tenant)
    if not can_move(TENANT_TRANSITIONS, doc.status, "Rejected") or doc.status == "Rejected":
        frappe.throw(f"A {doc.status} school cannot be rejected", frappe.ValidationError)
    if frappe.db.sql("SELECT name FROM `tabSaaS Provisioning Job` WHERE tenant = %s AND status IN ('Queued', 'Running') "
                     "FOR UPDATE", (doc.name,)):
        frappe.throw("The school has a provisioning job in progress", frappe.ValidationError)
    doc.update({"status": "Rejected", "approved_by": None, "approved_on": None, "approval_note": reason})
    _save(doc)
    return {"tenant": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def grant_billing_exception(subscription, kind, note):
    """Let a school have a site without paying first: an approved free trial, or an internal / demo school."""
    _admin()
    if kind not in (FREE_TRIAL, INTERNAL):
        frappe.throw(f"Choose {FREE_TRIAL} or {INTERNAL}", frappe.ValidationError)
    note = _note(note, kind)
    doc = _lock("SaaS Subscription", subscription)
    if doc.status in ("Cancelled", "Suspended"):
        frappe.throw(f"A {doc.status} subscription cannot be given an exception", frappe.ValidationError)
    if kind == FREE_TRIAL and (doc.status != "Trial" or not doc.ends_on or getdate(doc.ends_on) < getdate(nowdate())):
        frappe.throw("A free trial needs a Trial subscription with an end date that has not passed", frappe.ValidationError)
    doc.update({"billing_exception": kind, "exception_approved_by": frappe.session.user,
                "exception_approved_on": now_datetime(), "exception_note": note})
    _save(doc)
    return {"subscription": doc.name, "billing_exception": kind}


@frappe.whitelist(methods=["POST"])
def revoke_billing_exception(subscription):
    _admin()
    doc = _lock("SaaS Subscription", subscription)
    doc.update({f: None for f in EXCEPTION_FIELDS})
    _save(doc)
    return {"subscription": doc.name, "billing_exception": None}


@frappe.whitelist(methods=["GET"])
def status(tenant):
    """What the school form shows: can it be provisioned, and if not, why."""
    _admin()
    doc = frappe.get_doc("SaaS Tenant", tenant)
    return {"approved": approved(doc), "basis": commercial_basis(doc.name), "problems": problems(doc),
            "environment_problem": environment_problem()}
