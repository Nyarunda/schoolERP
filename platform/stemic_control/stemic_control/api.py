"""Authenticated Stemic control-plane APIs; no web-facing shell execution."""

import re
import secrets

import frappe
from frappe.utils import now_datetime

from stemic_control import config, policy
from stemic_control.policy import HOST, RESERVED, SLUG  # noqa: F401  (re-exported for callers and tests)

DEFAULT_PLATFORM_DOMAIN = "stemicschools.com"
DEFAULT_DOH_URL = "https://cloudflare-dns.com/dns-query"


def platform_domain() -> str:
    """The domain school subdomains live under. Set `stemic_platform_domain` in site_config to change it."""
    return (config.get("stemic_platform_domain") or DEFAULT_PLATFORM_DOMAIN).strip().lower().rstrip(".")


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


def _hostname(value):
    host = (value or "").strip().lower().rstrip(".")
    if not policy.is_hostname(host):
        frappe.throw("Invalid DNS hostname", frappe.ValidationError)
    return host


@frappe.whitelist(methods=["POST"])
def register_tenant(school_name, slug, admin_email, agent=None, contact_phone=None):
    _admin()
    slug = (slug or "").strip().lower()
    if not SLUG.fullmatch(slug) or slug in RESERVED:
        frappe.throw("Invalid or reserved tenant slug", frappe.ValidationError)
    if not school_name or not frappe.utils.validate_email_address(admin_email):
        frappe.throw("School name and valid email required", frappe.ValidationError)
    if frappe.db.exists("SaaS Tenant", slug):
        frappe.throw("Slug already taken", frappe.ValidationError)
    if agent and not frappe.db.exists("SaaS Agent", agent):
        frappe.throw("Unknown agent", frappe.ValidationError)
    return frappe.get_doc({"doctype": "SaaS Tenant", "school_name": school_name,
        "slug": slug, "admin_email": admin_email, "agent": agent, "contact_phone": (contact_phone or "").strip() or None,
        "status": "Draft"}).insert().name


@frappe.whitelist(methods=["POST"])
def request_domain(tenant, hostname):
    """Claim a hostname for a school. The school's own platform subdomain is verified at once (the platform owns
    that DNS); a custom domain stays Pending Verification until verify_domain finds the TXT record."""
    _admin()
    school = frappe.get_doc("SaaS Tenant", tenant)
    school.check_permission("read")
    host = _hostname(hostname)
    base = platform_domain()
    if host in policy.reserved_hosts(base):
        frappe.throw("Reserved platform hostname", frappe.ValidationError)
    managed = policy.subdomain_of(host, base)
    if managed and host != f"{school.slug}.{base}":
        frappe.throw("Only the school's reserved subdomain is allowed", frappe.PermissionError)
    if frappe.db.exists("SaaS Domain", host):
        frappe.throw("Hostname already registered", frappe.ValidationError)
    token = secrets.token_urlsafe(32)
    domain = frappe.get_doc({"doctype": "SaaS Domain", "tenant": tenant, "hostname": host,
        "domain_type": "Stemic Subdomain" if managed else "Custom Domain",
        "status": "Verified" if managed else "Pending Verification",
        "verified_on": now_datetime() if managed else None,
        "verification_token": token}).insert()
    return {"domain": domain.name, "hostname": host, "status": domain.status,
        "verification_record": None if managed else policy.VERIFICATION_PREFIX + host,
        "verification_value": None if managed else token}


def _txt_records(name: str) -> list[str]:
    """TXT values for `name` via DNS-over-HTTPS (`stemic_dns_over_https` in site_config to change the resolver)."""
    import requests

    r = requests.get(config.get("stemic_dns_over_https") or DEFAULT_DOH_URL,
        params={"name": name, "type": "TXT"}, headers={"accept": "application/dns-json"}, timeout=10)
    r.raise_for_status()
    return policy.txt_values(r.json())


@frappe.whitelist(methods=["POST"])
def verify_domain(domain):
    """Mark a custom domain Verified once `_stemic-verification.<host>` has a TXT record with its token."""
    _admin()
    doc = frappe.get_doc("SaaS Domain", domain)
    doc.check_permission("write")
    if doc.status in ("Verified", "Active"):
        return {"domain": doc.name, "status": doc.status}
    if doc.status != "Pending Verification":
        frappe.throw(f"A {doc.status} domain cannot be verified", frappe.ValidationError)
    record = policy.VERIFICATION_PREFIX + doc.hostname
    try:
        found = _txt_records(record)
    except Exception:
        frappe.log_error(title=f"DNS lookup failed for {record}")
        frappe.throw("Could not look up DNS right now. Try again shortly.", frappe.ValidationError)
    if not any(secrets.compare_digest(value, doc.verification_token or "") for value in found):
        frappe.throw(f"TXT record {record} with the verification value was not found yet", frappe.ValidationError)
    doc.db_set({"status": "Verified", "verified_on": now_datetime()})
    return {"domain": doc.name, "status": "Verified"}


@frappe.whitelist(methods=["POST"])
def queue_provisioning(tenant, request_key):
    _admin()
    school = frappe.get_doc("SaaS Tenant", tenant)
    school.check_permission("read")
    if school.status not in ("Approved", "Pending", "Failed"):
        frappe.throw("Only an approved school can be queued for provisioning", frappe.ValidationError)
    if not request_key or len(request_key) > 100 or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_key):
        frappe.throw("Invalid idempotency key", frappe.ValidationError)

    def existing_job():
        row = frappe.db.get_value("SaaS Provisioning Job", {"idempotency_key": request_key}, ["name", "tenant"], as_dict=True)
        if row and row.tenant != tenant:
            frappe.throw("Key already allocated to another tenant", frappe.PermissionError)
        return row.name if row else None

    # Serialize provisioning for one tenant, including distinct idempotency keys.
    # The lock is held until the request transaction commits.
    frappe.db.sql("SELECT name FROM `tabSaaS Tenant` WHERE name = %s FOR UPDATE", (tenant,))
    name = existing_job()
    if name:
        return name
    from stemic_control import onboarding

    school = frappe.get_doc("SaaS Tenant", tenant)  # as it is now that we hold the lock
    refused = onboarding.problems(school, lock=True)
    if refused:
        frappe.throw("Cannot queue this school: " + "; ".join(refused), frappe.ValidationError)
    # A job under this same key is not a competitor: it is the answer (its insert may not be visible to this
    # transaction's snapshot yet, in which case the duplicate-key handling below returns it). A locking read:
    # after waiting for the tenant lock, a plain read would miss a job the other request just committed.
    active = frappe.db.sql(
        "SELECT name FROM `tabSaaS Provisioning Job` WHERE tenant = %s AND action = 'Create Site' "
        "AND status IN ('Queued', 'Running') AND idempotency_key != %s LIMIT 1 FOR UPDATE", (tenant, request_key))
    active = active[0][0] if active else None
    if active:
        frappe.throw(f"An active provisioning job already exists: {active}", frappe.ValidationError)
    try:
        job = frappe.get_doc({"doctype": "SaaS Provisioning Job", "tenant": tenant,
            "idempotency_key": request_key, "action": "Create Site", "status": "Queued"}).insert()
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        # Another request with the same key won the race: answer with its job
        frappe.db.rollback()
        return existing_job()
    if school.status != "Pending":
        school.status = "Pending"
        school.save()
    from stemic_control import provisioner

    provisioner.enqueue(job.name)  # no-op unless the local provisioner is switched on
    # The privileged infrastructure provisioner must independently validate and claim this job.
    # Merely queueing a job does NOT create a site or run an OS command.
    return job.name


@frappe.whitelist(methods=["POST"])
def record_job_result(job, status, error=None):
    """Move a provisioning job on (Running / Succeeded / Failed) and its tenant with it.

    Called by the operator today; the privileged provisioner will call it once it has its own credentials."""
    _admin()
    doc = frappe.get_doc("SaaS Provisioning Job", job)
    doc.check_permission("write")
    if not policy.can_move(policy.JOB_TRANSITIONS, doc.status, status):
        frappe.throw(f"A {doc.status} job cannot become {status}", frappe.ValidationError)
    if doc.action == "Create Site" and status == "Succeeded":
        frappe.throw(
            "Site activation requires the infrastructure provisioner; completion is disabled until verified provisioning is implemented",
            frappe.ValidationError,
        )
    updates = {"status": status}
    if status == "Running":
        updates["attempts"] = (doc.attempts or 0) + 1
    if status == "Failed":
        updates["last_error"] = (error or "")[:10000] or "Failed without a message"
    doc.db_set(updates)
    tenant_status = policy.JOB_EFFECT.get((doc.action, status))
    if tenant_status:
        tenant = frappe.get_doc("SaaS Tenant", doc.tenant)
        if tenant.status != tenant_status:
            tenant.status = tenant_status
            tenant.save()
    return {"job": doc.name, "status": status, "tenant_status": tenant_status}


@frappe.whitelist(methods=["POST"])
def set_tenant_status(tenant, status):
    """Operator switch: suspend or resume a school. Other changes go through provisioning jobs."""
    _admin()
    if status not in ("Suspended", "Active"):
        frappe.throw("Only Suspended or Active can be set by hand", frappe.ValidationError)
    doc = frappe.get_doc("SaaS Tenant", tenant)
    changed = doc.status != status
    doc.status = status
    doc.save()  # SaasTenant.validate refuses moves the policy does not allow
    if changed:
        from stemic_control import communications

        communications.queue("Suspended" if status == "Suspended" else "Resumed", tenant=doc.name)
    return {"tenant": doc.name, "status": doc.status}


@frappe.whitelist(methods=["GET"])
def overview():
    _admin()
    return {"tenants": frappe.db.count("SaaS Tenant"),
            "active_tenants": frappe.db.count("SaaS Tenant", {"status": "Active"}),
            "active_subscriptions": frappe.db.count("SaaS Subscription", {"status": "Active"}),
            "agents": frappe.db.count("SaaS Agent", {"status": "Active"}),
            "queued_jobs": frappe.db.count("SaaS Provisioning Job", {"status": "Queued"})}


@frappe.whitelist(methods=["GET"])
def dashboard_metrics():
    """Real counts for the four admin dashboard views; never expose global counts to agents."""
    _admin()
    count = frappe.db.count
    return {
        "home": {
            "total_schools": count("SaaS Tenant"),
            "active_schools": count("SaaS Tenant", {"status": "Active"}),
            "active_subscriptions": count("SaaS Subscription", {"status": "Active"}),
            "pending_provisioning": count("SaaS Provisioning Job", {"status": ["in", ["Queued", "Running"]]}),
        },
        "schools": {
            "total_schools": count("SaaS Tenant"),
            "active_schools": count("SaaS Tenant", {"status": "Active"}),
            "trial_schools": count("SaaS Subscription", {"status": "Trial"}),
            "pending_provisioning": count("SaaS Provisioning Job", {"status": ["in", ["Queued", "Running"]]}),
            "failed_provisioning": count("SaaS Provisioning Job", {"status": "Failed"}),
            "pending_domains": count("SaaS Domain", {"status": "Pending Verification"}),
        },
        "billing": {
            "active_subscriptions": count("SaaS Subscription", {"status": "Active"}),
            "trial_subscriptions": count("SaaS Subscription", {"status": "Trial"}),
            "past_due": count("SaaS Subscription", {"status": "Past Due"}),
            "expiring_soon": count("SaaS Subscription", {"ends_on": ["between", [
                frappe.utils.today(), frappe.utils.add_days(frappe.utils.today(), 30)
            ]], "status": ["in", ["Active", "Trial", "Grace"]]}),
        },
        "agents": {
            "total_agents": count("SaaS Agent"),
            "active_agents": count("SaaS Agent", {"status": "Active"}),
            "referred_schools": count("SaaS Tenant", {"agent": ["is", "set"]}),
            "referred_active_schools": count("SaaS Tenant", {"agent": ["is", "set"], "status": "Active"}),
        },
    }


@frappe.whitelist(methods=["GET"])
def platform_info():
    """What the admin screens need to preview hostnames before a domain is claimed."""
    _admin()
    return {"platform_domain": platform_domain(), "reserved": sorted(RESERVED)}


@frappe.whitelist(methods=["POST"])
def provision_now(job):
    """Hand a queued Create Site job to the local provisioner's background worker."""
    _admin()
    from stemic_control import provisioner

    if not provisioner.enabled():
        frappe.throw("The local provisioner is not switched on (stemic_local_provisioner in site_config)", frappe.ValidationError)
    if frappe.db.get_value("SaaS Provisioning Job", job, "status") != "Queued":
        frappe.throw("Only a Queued job can be provisioned", frappe.ValidationError)
    provisioner.enqueue(job)
    return {"job": job, "status": "Queued for the provisioner"}


@frappe.whitelist(methods=["POST"])
def site_access(tenant):
    """Where a provisioned school site is and its Administrator password (platform admins only)."""
    _admin()
    from frappe.utils.password import get_decrypted_password

    doc = frappe.get_doc("SaaS Tenant", tenant)
    doc.check_permission("read")
    if not doc.canonical_site:
        frappe.throw("This school has no site yet", frappe.ValidationError)
    return {"site": doc.canonical_site, "user": "Administrator",
            "password": get_decrypted_password("SaaS Tenant", tenant, "site_admin_password", raise_exception=False)}


@frappe.whitelist(methods=["POST"])
def process_queue_now():
    """Manual run of the provisioner's 5-minute check: hand waiting jobs to a worker, fail abandoned ones."""
    _admin()
    from stemic_control import provisioner

    if not provisioner.enabled():
        frappe.throw("The local provisioner is not switched on (stemic_local_provisioner in site_config)", frappe.ValidationError)
    return {"handed_to_worker": provisioner.process_queue()}


@frappe.whitelist(methods=["POST"])
def provision_tenant_now(tenant):
    """Manual nudge for a school stuck in Pending: hand its queued Create Site job to the provisioner."""
    _admin()
    job = frappe.db.get_value("SaaS Provisioning Job", {"tenant": tenant, "action": "Create Site", "status": "Queued"},
                              "name", order_by="creation desc")
    if not job:
        frappe.throw("This school has no queued site job. Use Queue Provisioning.", frappe.ValidationError)
    return provision_now(job)


def _background_job_status(job_id):
    """The background (RQ) job's own status: queued, started, finished, failed... or None if there is none."""
    try:
        from frappe.utils.background_jobs import get_job

        job = get_job(job_id)
        return job.get_status() if job else None
    except Exception:
        return None


@frappe.whitelist(methods=["GET"])
def provisioning_progress(tenant):
    """What the provisioning dialog shows: the school's latest site job, where it is, and why it stopped if it did."""
    _admin()
    school = frappe.get_doc("SaaS Tenant", tenant)
    school.check_permission("read")
    job = frappe.db.get_value("SaaS Provisioning Job", {"tenant": tenant, "action": "Create Site"},
                              ["name", "status", "attempts", "last_error", "environment", "creation", "modified"],
                              as_dict=True, order_by="creation desc")
    try:
        from frappe.utils.background_jobs import get_workers

        workers = len(get_workers())
    except Exception:
        workers = None  # Redis not reachable: unknown
    from stemic_control import provisioner

    out = {"tenant_status": school.status, "site": school.canonical_site, "workers": workers,
           "local_provisioner": provisioner.enabled(), "now": str(now_datetime()), "job": None}
    if job:
        error = (job.last_error or "").strip()
        refused = error.startswith("Refused:")
        out["job"] = {
            "name": job.name, "status": job.status, "attempts": job.attempts, "environment": job.environment,
            "queued_on": str(job.creation), "updated_on": str(job.modified), "refused": refused,
            # a refusal's reasons, or the error's first useful line (not a traceback's header or frames)
            "reasons": [r.strip().rstrip(".") for r in error[len("Refused:"):].split(";") if r.strip()] if refused else [],
            "error": next((line.strip() for line in error.splitlines()
                           if line.strip() and not line.startswith(("Traceback", "  File", "    "))), "")[:300],
            # what became of a half-made site (provisioner._drop_partial_site's line), if anything was made
            "cleanup": next((line.strip() for line in error.splitlines() if "partly created site" in line), ""),
            "worker_job": _background_job_status(f"stemic-provision-{job.name}"),
        }
    return out


@frappe.whitelist(methods=["GET"])
def plan_catalogue():
    """School ERP modules a plan can include, for the plan form."""
    _admin()
    return [{"code": code, "label": label} for code, label in policy.MODULES.items()]


@frappe.whitelist(methods=["GET"])
def plan_summary(plan):
    """Who is on a plan and what it earns."""
    _admin()
    by_status = {}
    for status in frappe.get_all("SaaS Subscription", filters={"plan": plan}, pluck="status"):
        by_status[status] = by_status.get(status, 0) + 1
    price = frappe.db.get_value("SaaS Plan", plan, "monthly_price") or 0
    return {"by_status": by_status, "total": sum(by_status.values()), "mrr": price * by_status.get("Active", 0)}


@frappe.whitelist(methods=["GET"])
def subscription_summary(subscription):
    """What the subscription form shows next to its fields: the school, the plan and the license in force."""
    sub = frappe.get_doc("SaaS Subscription", subscription)
    sub.check_permission("read")
    from stemic_control import licensing

    tenant = frappe.db.get_value("SaaS Tenant", sub.tenant, ["school_name", "status", "canonical_site"], as_dict=True) or {}
    plan = frappe.db.get_value("SaaS Plan", sub.plan, ["monthly_price", "student_limit", "enabled"], as_dict=True) or {}
    license = frappe.db.get_value("SaaS License", {"subscription": sub.name}, ["name", "status", "expires_on", "issued_on"],
                                  as_dict=True, order_by="creation desc")
    return {"tenant": tenant, "plan": plan, "modules": [policy.MODULES[m] for m in licensing.plan_modules(sub.plan)],
            "license": license, "can_sign": licensing.can_sign(), "next": sorted(policy.SUBSCRIPTION_TRANSITIONS.get(sub.status, ())),
            "licensable": sub.status in policy.LICENSABLE}


@frappe.whitelist(methods=["POST"])
def set_subscription_status(subscription, status, payment_ref=None):
    """Operator billing switch (Activate, Past Due, Grace, Suspend, Cancel). Activating needs the payment reference."""
    _admin()
    doc = frappe.get_doc("SaaS Subscription", subscription)
    if status == "Active" and not (payment_ref or "").strip():
        frappe.throw("Enter the payment reference to activate a subscription", frappe.ValidationError)
    doc.status = status
    if payment_ref:
        doc.external_payment_ref = payment_ref.strip()
    doc.save()  # SaaSSubscription.validate refuses moves the policy does not allow
    return {"subscription": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def renew_subscription(subscription, months, payment_ref, mode="M-Pesa"):
    """A school paid for another period: invoice it (or use the renewal invoice already raised) and record the
    payment. The payment extends the subscription, makes it Active and earns the agent's commission."""
    _admin()
    months = int(months)
    if months not in (1, 3, 6, 12, 24):
        frappe.throw("Renew for 1, 3, 6, 12 or 24 months", frappe.ValidationError)
    if not (payment_ref or "").strip():
        frappe.throw("Enter the payment reference for the renewal", frappe.ValidationError)
    from frappe.utils import nowdate

    from stemic_control import billing

    if frappe.db.get_value("SaaS Subscription", subscription, "status") == "Cancelled":
        frappe.throw("A cancelled subscription cannot be renewed; start a new one", frappe.ValidationError)
    invoice = billing.open_invoice(subscription) or billing._create_invoice(subscription, months)
    outstanding = frappe.db.get_value("SaaS Invoice", invoice, "outstanding")
    payment = frappe.get_doc({"doctype": "SaaS Payment", "invoice": invoice, "amount": outstanding, "mode": mode,
                              "reference": payment_ref.strip(), "payment_date": nowdate()})
    payment.insert(ignore_permissions=True)
    payment.submit()
    return {"subscription": subscription, "invoice": invoice, "payment": payment.name,
            "ends_on": str(frappe.db.get_value("SaaS Subscription", subscription, "ends_on"))}


@frappe.whitelist(methods=["POST"])
def issue_license(subscription):
    """Sign a School ERP key from the subscription (plan modules, student limit, end date, the school's site)."""
    _admin()
    from stemic_control import licensing

    return {"license": licensing.issue(subscription)}


@frappe.whitelist(methods=["POST"])
def revoke_license(license):
    """Mark a key revoked. A key already pasted into a school keeps working until it expires (it is checked offline)."""
    _admin()
    if frappe.db.get_value("SaaS License", license, "status") != "Issued":
        frappe.throw("Only an issued license can be revoked", frappe.ValidationError)
    frappe.db.set_value("SaaS License", license, "status", "Revoked")
    return {"license": license, "status": "Revoked"}


@frappe.whitelist(methods=["GET"])
def operations_queue(per_group=3):
    """What needs an operator, grouped, newest first: each group's total, a few items naming the school, and the list
    filters behind "View all". Every group is always present, so a busy one never hides another."""
    _admin()
    per_group = max(1, min(int(per_group), 10))
    schools = {}

    def school(tenant):
        if tenant not in schools:
            schools[tenant] = frappe.db.get_value("SaaS Tenant", tenant, "school_name") or tenant
        return schools[tenant]

    def last_error(tenant):
        error = frappe.db.get_value("SaaS Provisioning Job", {"tenant": tenant, "status": "Failed"}, "last_error",
                                   order_by="modified desc") or ""
        return next((line.strip() for line in error.splitlines() if line.strip()), "")[:140]

    groups = []
    # (key, label, severity, doctype, filters, row fields, item -> (school, detail))
    for key, label, severity, doctype, filters, fields, describe in (
        ("failed_sites", "Sites that could not be created", "critical", "SaaS Tenant", {"status": "Failed"},
         ["name", "school_name", "modified"], lambda r: (r.school_name, last_error(r.name) or r.name)),
        ("overdue", "Payments overdue", "critical", "SaaS Subscription", {"status": ["in", ["Past Due", "Grace"]]},
         ["name", "tenant", "plan", "status", "modified"], lambda r: (school(r.tenant), f"{r.plan} · {r.status}")),
        ("unpaid_invoices", "Invoices overdue", "critical", "SaaS Invoice", {"status": "Overdue", "docstatus": 1},
         ["name", "tenant", "outstanding", "currency", "modified"],
         lambda r: (school(r.tenant), f"{r.name} · {r.currency or ''} {r.outstanding:,.0f} owed".replace("  ", " "))),
        ("dns", "Domains waiting for DNS", "warning", "SaaS Domain", {"status": "Pending Verification"},
         ["name", "tenant", "modified"], lambda r: (school(r.tenant), r.name)),
        ("approval", "Schools waiting for approval", "warning", "SaaS Tenant", {"status": "Pending Approval"},
         ["name", "school_name", "modified"], lambda r: (r.school_name, r.name)),
        ("creating", "Sites being created", "info", "SaaS Tenant", {"status": ["in", ["Pending", "Provisioning"]]},
         ["name", "school_name", "status", "modified"], lambda r: (r.school_name, r.status)),
    ):
        rows = frappe.get_all(doctype, filters=filters, fields=fields, order_by="modified desc", limit_page_length=per_group)
        items = []
        for row in rows:
            name_of_school, detail = describe(row)
            items.append({"doctype": doctype, "name": row.name, "school": name_of_school, "detail": detail,
                          "modified": str(row.modified)})
        groups.append({"key": key, "label": label, "severity": severity, "doctype": doctype, "filters": filters,
                       "count": frappe.db.count(doctype, filters), "items": items})
    # first: the machinery itself (stemic_control.health); when it is down, everything below stops moving
    from stemic_control import health

    problems = health.check()
    groups.insert(0, {"key": "background", "label": "Background jobs not running", "severity": "critical",
                      "doctype": "Stemic Settings", "filters": {}, "count": len(problems),
                      "items": [{"doctype": "Stemic Settings", "name": "Stemic Settings", "school": p["message"],
                                 "detail": p["fix"], "modified": str(now_datetime())} for p in problems[:per_group]]})
    return {"groups": groups, "total": sum(g["count"] for g in groups)}
