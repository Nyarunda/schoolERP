"""Authenticated Stemic control-plane APIs; no web-facing shell execution."""
import re
import secrets
import frappe

SLUG = re.compile(r"^[a-z][a-z0-9-]{2,48}$")
HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}$")
RESERVED = {"admin", "www", "api", "mail", "billing", "agents", "support", "status", "app"}

def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)

def _hostname(value):
    host = (value or "").strip().lower().rstrip(".")
    if not HOST.fullmatch(host):
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
    if frappe.db.exists("SaaS Tenant", {"slug": slug}):
        frappe.throw("Slug already taken", frappe.ValidationError)
    if agent and not frappe.db.exists("SaaS Agent", agent):
        frappe.throw("Unknown agent", frappe.ValidationError)
    return frappe.get_doc({"doctype": "SaaS Tenant", "school_name": school_name,
        "slug": slug, "admin_email": admin_email, "agent": agent, "status": "Draft"}).insert().name

@frappe.whitelist(methods=["POST"])
def request_domain(tenant, hostname):
    _admin()
    school = frappe.get_doc("SaaS Tenant", tenant)
    school.check_permission("read")
    host = _hostname(hostname)
    if host == "stemischools.com" or host in {f"{x}.stemischools.com" for x in RESERVED}:
        frappe.throw("Reserved platform hostname", frappe.ValidationError)
    managed = host.endswith(".stemischools.com")
    if managed and host != f"{school.slug}.stemischools.com":
        frappe.throw("Only the school's reserved subdomain is allowed", frappe.PermissionError)
    if frappe.db.exists("SaaS Domain", {"hostname": host}):
        frappe.throw("Hostname already registered", frappe.ValidationError)
    token = secrets.token_urlsafe(32)
    domain = frappe.get_doc({"doctype": "SaaS Domain", "tenant": tenant,
        "hostname": host, "domain_type": "Stemic Subdomain" if managed else "Custom Domain",
        "status": "Pending Verification", "verification_token": token}).insert()
    return {"domain": domain.name, "hostname": host, "status": "Pending Verification",
        "verification_record": None if managed else "_stemic-verification." + host,
        "verification_value": None if managed else token}

@frappe.whitelist(methods=["POST"])
def queue_provisioning(tenant, request_key):
    _admin()
    school = frappe.get_doc("SaaS Tenant", tenant)
    school.check_permission("read")
    if school.status not in ("Draft", "Pending", "Failed"):
        frappe.throw("Tenant is not eligible for provisioning", frappe.ValidationError)
    if not request_key or len(request_key) > 100 or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_key):
        frappe.throw("Invalid idempotency key", frappe.ValidationError)
    existing = frappe.db.get_value("SaaS Provisioning Job", {"idempotency_key": request_key}, ["name", "tenant"], as_dict=True)
    if existing:
        if existing.tenant != tenant:
            frappe.throw("Key already allocated to another tenant", frappe.PermissionError)
        return existing.name
    job = frappe.get_doc({"doctype": "SaaS Provisioning Job", "tenant": tenant,
        "idempotency_key": request_key, "action": "Create Site", "status": "Queued"}).insert()
    # The privileged infrastructure provisioner must independently validate and claim this job.
    # Merely queueing a job does NOT create a site or run an OS command.
    return job.name

@frappe.whitelist(methods=["GET"])
def overview():
    _admin()
    return {"tenants": frappe.db.count("SaaS Tenant"),
            "active_tenants": frappe.db.count("SaaS Tenant", {"status": "Active"}),
            "active_subscriptions": frappe.db.count("SaaS Subscription", {"status": "Active"}),
            "agents": frappe.db.count("SaaS Agent", {"status": "Active"}),
            "queued_jobs": frappe.db.count("SaaS Provisioning Job", {"status": "Queued"})}
