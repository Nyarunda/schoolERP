"""Onboard a School: one form instead of five. It registers the school, gives it a subscription, starts its free trial
(or records its first payment, or marks it internal), claims its addresses, and approves it and queues its site.

Every step goes through the same guarded functions an operator would press one by one (api.register_tenant,
onboarding.approve_tenant, api.queue_provisioning, ...), in one transaction: if any step is refused, nothing is kept,
and the operator is told which step and why. The provisioner still checks everything again before it builds.
"""

import re

import frappe
from frappe.utils import add_days, cint, flt, nowdate

from stemic_control import policy

STARTS = ("Free trial", "Paid", "Internal / Demo")
WHEN = ("build", "approval", "draft")  # approve and build now / send for approval / keep as a draft
PAY_MODES = ("M-Pesa", "Bank Transfer", "Cheque", "Cash")


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


def suggest_slug(school_name: str) -> str:
    """'St. Teresa's Girls High School' -> 'st-teresas-girls'. Drops the generic words a school name usually ends with."""
    words = re.sub(r"[^a-z0-9\s-]", "", (school_name or "").lower().replace("&", " and ")).split()
    generic = {"school", "schools", "high", "secondary", "primary", "academy", "the", "and", "of", "junior", "senior",
               "girls", "boys", "mixed", "day", "boarding", "centre", "center", "college", "preparatory", "prep"}
    keep = [w for w in words if w not in generic] or words
    slug = "-".join(keep[:3]).strip("-")
    if slug and not slug[0].isalpha():
        slug = "s-" + slug
    return slug[:40]


@frappe.whitelist(methods=["GET"])
def check_slug(slug=None, school_name=None, domain=None):
    """Is this address free on `domain` (default: the platform's default domain)? Suggests one from the school's name
    when no slug is given, and a free variant if taken."""
    _admin()
    from stemic_control.api import offered_domains

    domain = (domain or "").strip().lower().rstrip(".") or offered_domains()[0]
    slug = (slug or suggest_slug(school_name or "")).strip().lower()
    problem = None
    if domain not in offered_domains():
        problem = f"{domain} is not one of the domains offered for new schools"
    elif not slug:
        problem = "Type the school's name or an address"
    elif not policy.SLUG.fullmatch(slug):
        problem = "Use 3 to 49 lower-case letters, digits or hyphens, starting with a letter"
    elif slug in policy.RESERVED:
        problem = "That name is reserved for the platform"
    elif frappe.db.exists("SaaS Tenant", slug):
        problem = f"Already used by {frappe.db.get_value('SaaS Tenant', slug, 'school_name')}"
    elif frappe.db.exists("SaaS Domain", f"{slug}.{domain}"):
        problem = "That address is already claimed"
    alternative = None
    if problem and slug and policy.SLUG.fullmatch(slug + "-2"):
        for n in range(2, 30):
            candidate = f"{slug}-{n}"
            if not frappe.db.exists("SaaS Tenant", candidate):
                alternative = candidate
                break
    return {"slug": slug, "ok": not problem, "problem": problem, "alternative": alternative, "domain": domain,
            "host": f"{slug}.{domain}" if slug else None}


@frappe.whitelist(methods=["GET"])
def options():
    """What the Onboard a School form offers, and what it should warn about before anyone presses Save."""
    _admin()
    from stemic_control import licensing, onboarding
    from stemic_control.api import offered_domains, platform_domain
    from stemic_control.billing import settings

    s = settings()
    plans = frappe.get_all("SaaS Plan", filters={"enabled": 1}, fields=["name", "monthly_price", "student_limit", "modules"],
                           order_by="monthly_price asc")
    for p in plans:
        p.modules = [policy.MODULES[m] for m in licensing.plan_modules(p.name)]
    return {
        "platform_domain": platform_domain(),
        "platform_domains": offered_domains(),
        "plans": plans,
        "agents": frappe.get_all("SaaS Agent", filters={"status": "Active"}, fields=["name", "agent_name", "commission_rate"],
                                 order_by="agent_name"),
        "defaults": {"plan": s.get("default_plan") if s.get("default_plan") in [p.name for p in plans] else (plans[0].name if plans else None),
                     "trial_days": cint(s.get("default_trial_days")) or 30,
                     "start": s.get("default_start") or "Free trial",
                     "when": "build" if cint(s.get("build_on_onboard") if s.get("build_on_onboard") is not None else 1) else "approval",
                     "months": cint(s.billing_months) or 12},
        "currency": s.currency or "KES",
        "environment_problem": onboarding.environment_problem(),
        "can_sign": licensing.can_sign(),
        "auto_license": cint(s.get("auto_issue_license") if s.get("auto_issue_license") is not None else 1),
        "pay_modes": list(PAY_MODES),
    }


def _step(steps, label, fn, *args, **kwargs):
    """Run one step; on refusal, say which step it was (the whole transaction is rolled back by the caller)."""
    try:
        out = fn(*args, **kwargs)
    except frappe.ValidationError as e:
        frappe.clear_messages()
        raise frappe.ValidationError(f"{label}: {e}") from e
    steps.append(label)
    return out


@frappe.whitelist(methods=["POST"])
def onboard_school(school_name, admin_email, plan, start="Free trial", slug=None, contact_phone=None, agent=None,
                   trial_days=None, months=None, amount=None, payment_mode="M-Pesa", payment_ref=None, note=None,
                   custom_domain=None, when="build", platform_domain=None):
    """Register a school and take it as far as `when` says, in one transaction. Returns what was done and what is next."""
    _admin()
    from stemic_control import api, onboarding

    on_domain = (platform_domain or "").strip().lower().rstrip(".") or api.platform_domain()
    school_name = (school_name or "").strip()
    if start not in STARTS:
        frappe.throw(f"Start must be one of {', '.join(STARTS)}", frappe.ValidationError)
    if when not in WHEN:
        frappe.throw("Choose build, approval or draft", frappe.ValidationError)
    if not plan or not frappe.db.get_value("SaaS Plan", plan, "enabled"):
        frappe.throw("Choose an enabled plan", frappe.ValidationError)
    slug = (slug or suggest_slug(school_name)).strip().lower()
    free = check_slug(slug, domain=on_domain)
    if not free["ok"]:
        frappe.throw(f"Address {slug}: {free['problem']}", frappe.ValidationError)
    if start == "Paid" and not (payment_ref or "").strip():
        frappe.throw("Enter the payment reference (e.g. the M-Pesa code) for a paid start", frappe.ValidationError)
    if payment_mode not in PAY_MODES:
        frappe.throw(f"Payment mode must be one of {', '.join(PAY_MODES)}", frappe.ValidationError)

    steps, warnings = [], []
    today = nowdate()
    who = frappe.utils.get_fullname(frappe.session.user)

    # 1. the school and its own address
    tenant = _step(steps, "Register the school", api.register_tenant, school_name, slug, (admin_email or "").strip(),
                   agent or None, contact_phone)
    frappe.db.set_value("SaaS Tenant", tenant, "platform_domain", on_domain, update_modified=False)
    _step(steps, f"Claim {slug}.{on_domain}", api.request_domain, tenant, f"{slug}.{on_domain}")

    # 2. its subscription, linked to the school so every screen shows it
    days = max(1, cint(trial_days) or 30)
    sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": tenant, "plan": plan, "agent": agent or None,
                          "status": "Trial", "starts_on": today,
                          "ends_on": add_days(today, days - 1) if start == "Free trial" else None})
    _step(steps, f"Subscribe to {plan}", sub.insert)
    frappe.db.set_value("SaaS Tenant", tenant, "subscription", sub.name, update_modified=False)

    # 3. why it may have a site: a free trial, an internal school, or a payment
    invoice = payment = None
    if start == "Free trial":
        _step(steps, f"Approve a {days}-day free trial", onboarding.grant_billing_exception, sub.name, onboarding.FREE_TRIAL,
              (note or "").strip() or f"{days}-day free trial, set up through Onboard a School by {who}")
    elif start == "Internal / Demo":
        _step(steps, "Mark it internal / demo", onboarding.grant_billing_exception, sub.name, onboarding.INTERNAL,
              (note or "").strip() or f"Internal or demo school, set up through Onboard a School by {who}")
    else:
        from stemic_control import billing

        n = cint(months) or cint(billing.settings().billing_months) or 12
        invoice = _step(steps, f"Invoice {n} month(s)", billing._create_invoice, sub.name, n)
        total = flt(frappe.db.get_value("SaaS Invoice", invoice, "outstanding"))
        paid = flt(amount) if flt(amount) > 0 else total
        if paid > total + 0.005:
            frappe.throw(f"The payment ({paid:,.2f}) is more than the invoice ({total:,.2f})", frappe.ValidationError)
        pay = frappe.get_doc({"doctype": "SaaS Payment", "invoice": invoice, "amount": paid, "mode": payment_mode,
                              "reference": payment_ref.strip(), "payment_date": today})
        _step(steps, f"Record the payment {payment_ref.strip()}", lambda: (pay.insert(ignore_permissions=True), pay.submit()))
        payment = pay.name
        if paid < total - 0.005:
            warnings.append(f"Part payment: {invoice} still has {total - paid:,.2f} to pay, so the site cannot be built until it is paid in full.")

    # 4. the school's own domain (verified later by its DNS record)
    domain = None
    if (custom_domain or "").strip():
        domain = _step(steps, f"Claim {custom_domain.strip().lower()}", api.request_domain, tenant, custom_domain)

    # 5. approve and build, or leave it for another admin
    if when in ("build", "approval"):
        _step(steps, "Send for approval", onboarding.submit_for_approval, tenant)
    job = None
    if when == "build":
        _step(steps, "Approve", onboarding.approve_tenant, tenant, (note or "").strip() or f"Approved through Onboard a School by {who}")
        school = frappe.get_doc("SaaS Tenant", tenant)
        refused = onboarding.problems(school)
        problem = onboarding.environment_problem()
        if refused:
            warnings.append("The site was not queued: " + "; ".join(refused) + ".")
        elif problem:
            warnings.append(f"The site was not queued, because this server may not build sites yet: {problem}. "
                            "Queue it from the school once that is fixed.")
        else:
            job = _step(steps, "Queue the site", api.queue_provisioning, tenant, f"onboard-{tenant}-{frappe.generate_hash(length=8)}")

    return {"tenant": tenant, "subscription": sub.name, "invoice": invoice, "payment": payment, "job": job,
            "domain": domain, "status": frappe.db.get_value("SaaS Tenant", tenant, "status"),
            "host": f"{slug}.{on_domain}", "steps": steps, "warnings": warnings}
