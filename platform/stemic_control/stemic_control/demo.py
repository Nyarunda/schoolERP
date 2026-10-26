"""Demo data for trying the control plane on a disposable admin site. Never run it on a real admin site.

    bench --site admin.localhost set-config stemic_allow_demo_data 1   (once, on a disposable site)
    bench --site admin.localhost execute stemic_control.demo.seed
    bench --site admin.localhost execute stemic_control.demo.clear

Re-running seed() is safe: existing demo records are left alone. Statuses that the API deliberately refuses to
reach (an Active school, a Succeeded Create Site job, a DNS-verified custom domain) are written directly so every
screen has something to show; they do not mean a site was really provisioned.
"""

import frappe
from frappe.utils import add_days, add_months, getdate, now_datetime, nowdate

from stemic_control.policy import MODULES

DEMO_NOTE = "Demo data (stemic_control.demo)"
EMAIL_DOMAIN = "demo.stemic.test"

PLANS = [
    # name, monthly price, student limit, modules
    ("Starter", 4500, 300, ["fees", "messaging"]),
    ("Standard", 9500, 800, ["fees", "messaging", "mpesa", "timetable", "staff", "transport"]),
    ("Premium", 18000, 0, ["fees", "messaging", "mpesa", "timetable", "staff", "transport", "exams", "portal", "welfare"]),
]
DESCRIPTIONS = {
    "Starter": "Small schools starting with fees and parent SMS.",
    "Standard": "Most day schools: fees, M-Pesa, timetable, staff and transport.",
    "Premium": "Everything, including exams, report cards and the parent portal.",
}
AGENTS = [("Wanjiku Mwangi", 10), ("Otieno Ochieng", 12), ("Chebet Kiprop", 8)]
# slug, school, status, plan, subscription status, agent index (None = direct), months ago registered, custom domain
SCHOOLS = [
    ("greenhill", "Greenhill Academy", "Active", "Premium", "Active", 0, 10, "portal.greenhill.ac.ke"),
    ("mogonga-pag", "Mogonga PAG Secondary", "Active", "Standard", "Active", 1, 9, None),
    ("st-teresas", "St. Teresa's Girls", "Active", "Standard", "Active", 0, 8, "fees.stteresas.sc.ke"),
    ("kisumu-day", "Kisumu Day School", "Active", "Starter", "Active", 2, 7, None),
    ("mt-kenya-prep", "Mt. Kenya Preparatory", "Active", "Premium", "Active", None, 6, None),
    ("rift-valley", "Rift Valley Academy", "Active", "Standard", "Past Due", 1, 5, None),
    ("baraka-junior", "Baraka Junior School", "Active", "Starter", "Trial", 2, 2, None),
    ("lakeside", "Lakeside Primary", "Suspended", "Starter", "Grace", 1, 6, None),
    ("nyeri-high", "Nyeri High School", "Provisioning", "Standard", "Trial", 0, 1, None),
    ("amani-hill", "Amani Hill School", "Pending", "Starter", "Trial", None, 1, "portal.amanihill.co.ke"),
    ("coast-academy", "Coast Academy Mombasa", "Pending", "Premium", "Trial", 2, 0, None),
    ("highway-sec", "Highway Secondary", "Failed", "Standard", None, 1, 1, None),
    ("tumaini", "Tumaini Children's Centre", "Draft", None, None, None, 0, None),
    ("elimu-bora", "Elimu Bora Academy", "Draft", None, None, 0, 0, None),
]


def _require_dev():
    # set `stemic_allow_demo_data: 1` in a disposable admin site's site_config to allow it there
    if not (frappe.conf.developer_mode or frappe.conf.get("allow_tests") or frappe.conf.get("stemic_allow_demo_data")):
        frappe.throw("Demo data is only for development or test sites (or set stemic_allow_demo_data)")


def _set(doctype, name, values):
    frappe.db.set_value(doctype, name, values, update_modified=False)


def seed():
    _require_dev()
    frappe.flags.in_demo = True
    for name, price, limit, modules in PLANS:
        if not frappe.db.exists("SaaS Plan", name):
            frappe.get_doc({"doctype": "SaaS Plan", "plan_name": name, "enabled": 1, "monthly_price": price, "description": DESCRIPTIONS[name],
                            "student_limit": limit, "modules": frappe.as_json(modules)}).insert()

    agents = []
    for full_name, rate in AGENTS:
        email = full_name.lower().replace(" ", ".") + "@" + EMAIL_DOMAIN
        if not frappe.db.exists("User", email):
            first, _sp, last = full_name.partition(" ")
            frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "last_name": last,
                            "send_welcome_email": 0, "roles": [{"role": "Stemic Agent"}]}).insert(ignore_permissions=True)
        agent = frappe.db.get_value("SaaS Agent", {"user": email})
        if not agent:
            agent = frappe.get_doc({"doctype": "SaaS Agent", "agent_name": full_name, "user": email,
                                    "status": "Active", "commission_rate": rate}).insert().name
        agents.append(agent)

    base = frappe.conf.get("stemic_platform_domain") or "stemischools.com"
    today = getdate(nowdate())
    for i, (slug, school, status, plan, sub_status, agent_ix, months_ago, custom) in enumerate(SCHOOLS):
        if frappe.db.exists("SaaS Tenant", slug):
            continue
        agent = agents[agent_ix] if agent_ix is not None else None
        registered = add_days(add_months(today, -months_ago), -((i * 3) % 20))  # spread within the month, never ahead
        tenant = frappe.get_doc({"doctype": "SaaS Tenant", "school_name": school, "slug": slug, "status": status,
                                 "admin_email": f"admin@{slug}.{EMAIL_DOMAIN}", "agent": agent, "notes": DEMO_NOTE}).insert()
        live = status in ("Active", "Suspended")
        _set("SaaS Tenant", slug, {"creation": f"{registered} 09:00:00",
                                   "canonical_site": f"{slug}.{base}" if live else None,
                                   "primary_domain": (custom if custom and live else f"{slug}.{base}") if live else None})

        if status != "Draft":
            sub = f"{slug}.{base}"
            frappe.get_doc({"doctype": "SaaS Domain", "tenant": tenant.name, "hostname": sub, "domain_type": "Stemic Subdomain",
                            "status": "Verified", "verified_on": now_datetime(), "verification_token": frappe.generate_hash(length=32)}).insert()
            if live:
                _set("SaaS Domain", sub, {"status": "Active", "is_primary": 0 if custom else 1})
        if custom:
            frappe.get_doc({"doctype": "SaaS Domain", "tenant": tenant.name, "hostname": custom, "domain_type": "Custom Domain",
                            "status": "Pending Verification", "verification_token": frappe.generate_hash(length=32)}).insert()
            if live:
                _set("SaaS Domain", custom, {"status": "Active", "verified_on": now_datetime(), "is_primary": 1})

        if status != "Draft":
            job = frappe.get_doc({"doctype": "SaaS Provisioning Job", "tenant": tenant.name, "action": "Create Site",
                                  "idempotency_key": f"demo-{slug}-create", "status": "Queued"}).insert()
            job_status = {"Pending": "Queued", "Provisioning": "Running", "Failed": "Failed"}.get(status, "Succeeded")
            _set("SaaS Provisioning Job", job.name, {
                "status": job_status, "attempts": 0 if job_status == "Queued" else (2 if job_status == "Failed" else 1),
                "last_error": "bench new-site timed out waiting for the database (demo)" if job_status == "Failed" else None,
                "creation": f"{add_days(registered, 1)} 10:00:00"})

        if plan and sub_status:
            starts = add_days(registered, 3)
            subscription = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": tenant.name, "plan": plan, "agent": agent,
                                           "starts_on": starts, "ends_on": add_months(starts, 12)}).insert()
            _set("SaaS Subscription", subscription.name, {"status": sub_status, "creation": f"{starts} 11:00:00",
                                                          "external_payment_ref": f"DEMO{1000 + i}" if sub_status == "Active" else None})
            _set("SaaS Tenant", slug, {"subscription": subscription.name})
            if live:
                lic = frappe.get_doc({"doctype": "SaaS License", "tenant": tenant.name, "subscription": subscription.name}).insert()
                plan_row = next(p for p in PLANS if p[0] == plan)
                _set("SaaS License", lic.name, {"status": "Issued" if status == "Active" else "Revoked",
                                                "expires_on": add_months(starts, 12), "signed_key": "DEMO-UNSIGNED-" + slug.upper(),
                                                "plan": plan, "site": f"{slug}.{base}", "issued_on": starts, "max_students": plan_row[2],
                                                "modules": "\n".join(MODULES[m] for m in MODULES if m in plan_row[3])})
    frappe.db.commit()
    frappe.flags.in_demo = False
    return {"schools": frappe.db.count("SaaS Tenant", {"notes": DEMO_NOTE}), "plans": len(PLANS), "agents": len(agents)}


def clear():
    """Remove everything seed() created."""
    _require_dev()
    slugs = frappe.get_all("SaaS Tenant", filters={"notes": DEMO_NOTE}, pluck="name")
    for doctype in ("SaaS License", "SaaS Provisioning Job", "SaaS Domain"):
        for name in frappe.get_all(doctype, filters={"tenant": ("in", slugs or [""])}, pluck="name"):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
    for name in slugs:
        frappe.db.set_value("SaaS Tenant", name, "subscription", None, update_modified=False)
    for name in frappe.get_all("SaaS Subscription", filters={"tenant": ("in", slugs or [""])}, pluck="name"):
        frappe.delete_doc("SaaS Subscription", name, force=True, ignore_permissions=True)
    for name in slugs:
        frappe.delete_doc("SaaS Tenant", name, force=True, ignore_permissions=True)
    for full_name, _rate in AGENTS:
        email = full_name.lower().replace(" ", ".") + "@" + EMAIL_DOMAIN
        for name in frappe.get_all("SaaS Agent", filters={"user": email}, pluck="name"):
            frappe.delete_doc("SaaS Agent", name, force=True, ignore_permissions=True)
        if frappe.db.exists("User", email):
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)
    for name, *_rest in PLANS:
        if frappe.db.exists("SaaS Plan", name) and not frappe.db.exists("SaaS Subscription", {"plan": name}):
            frappe.delete_doc("SaaS Plan", name, force=True, ignore_permissions=True)
    frappe.db.commit()
    return {"removed_schools": len(slugs)}
