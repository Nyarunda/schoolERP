"""Authenticated Stemic control-plane APIs; no web-facing shell execution."""

import re
import secrets

import frappe
from frappe.utils import now_datetime

from stemic_control import policy
from stemic_control.policy import HOST, RESERVED, SLUG  # noqa: F401  (re-exported for callers and tests)

DEFAULT_PLATFORM_DOMAIN = "stemischools.com"
DEFAULT_DOH_URL = "https://cloudflare-dns.com/dns-query"


def platform_domain() -> str:
    """The domain school subdomains live under. Set `stemic_platform_domain` in site_config to change it."""
    return (frappe.conf.get("stemic_platform_domain") or DEFAULT_PLATFORM_DOMAIN).strip().lower().rstrip(".")


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


def _hostname(value):
    host = (value or "").strip().lower().rstrip(".")
    if not policy.is_hostname(host):
        frappe.throw("Invalid DNS hostname", frappe.ValidationError)
    return host


@frappe.whitelist(methods=["POST"])
def register_tenant(school_name, slug, admin_email, agent=None):
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
        "slug": slug, "admin_email": admin_email, "agent": agent, "status": "Draft"}).insert().name


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

    r = requests.get(frappe.conf.get("stemic_dns_over_https") or DEFAULT_DOH_URL,
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
    if school.status not in ("Draft", "Pending", "Failed"):
        frappe.throw("Tenant is not eligible for provisioning", frappe.ValidationError)
    if not request_key or len(request_key) > 100 or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_key):
        frappe.throw("Invalid idempotency key", frappe.ValidationError)

    def existing_job():
        row = frappe.db.get_value("SaaS Provisioning Job", {"idempotency_key": request_key}, ["name", "tenant"], as_dict=True)
        if row and row.tenant != tenant:
            frappe.throw("Key already allocated to another tenant", frappe.PermissionError)
        return row.name if row else None

    name = existing_job()
    if name:
        return name
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
    doc.status = status
    doc.save()  # SaasTenant.validate refuses moves the policy does not allow
    return {"tenant": doc.name, "status": doc.status}


@frappe.whitelist(methods=["GET"])
def overview():
    _admin()
    return {"tenants": frappe.db.count("SaaS Tenant"),
            "active_tenants": frappe.db.count("SaaS Tenant", {"status": "Active"}),
            "active_subscriptions": frappe.db.count("SaaS Subscription", {"status": "Active"}),
            "agents": frappe.db.count("SaaS Agent", {"status": "Active"}),
            "queued_jobs": frappe.db.count("SaaS Provisioning Job", {"status": "Queued"})}
