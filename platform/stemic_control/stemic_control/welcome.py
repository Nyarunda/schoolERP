"""The welcome email a school's contact gets when its site is ready.

It carries the site's address, their username and a one-time link to set their own password (created on the school's
site by school_erp.setup.first_admin, valid 24 hours): no password is sent by email. Sent automatically when
provisioning succeeds; platform admins can send it again from the school (a fresh link each time).
"""

import json

import frappe
from frappe.utils import escape_html, now_datetime

from stemic_control import provisioner


def _first_admin(site, email, full_name):
    """Run school_erp.setup.first_admin.create on the school's site; returns its {"user", "link", "hours"}."""
    kwargs = repr({"email": email, "full_name": full_name})
    out = provisioner._frappe_cli("--site", site, "execute", "school_erp.setup.first_admin.create", "--kwargs", kwargs,
                                  timeout=180)
    for line in reversed(out.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            data = json.loads(line)
            if data.get("link"):
                return data
    raise provisioner.ProvisioningError(f"The school site did not return a set-password link for {email}")


def _billing(tenant):
    """The plan, what is paid and until when, and the latest invoice: for the welcome email's payment details."""
    from frappe.utils import fmt_money, formatdate

    sub = frappe.db.get_value("SaaS Subscription", tenant.subscription or {"tenant": tenant.name},
                              ["name", "plan", "status", "ends_on"], as_dict=True) if (
        tenant.subscription or frappe.db.exists("SaaS Subscription", {"tenant": tenant.name})) else None
    if not sub:
        return [], None
    price = frappe.db.get_value("SaaS Plan", sub.plan, "monthly_price")
    inv = frappe.get_all("SaaS Invoice", filters={"subscription": sub.name, "docstatus": 1},
                         fields=["name", "total", "outstanding", "status", "due_date", "currency"], order_by="creation desc", limit=1)
    inv = inv[0] if inv else None
    cur = (inv.currency if inv else None) or "KES"
    rows = [("Plan", f"{sub.plan}" + (f" ({fmt_money(price, currency=cur)} a month)" if price else "")),
            ("Subscription", sub.status + (f", paid until {formatdate(sub.ends_on)}" if sub.ends_on else ""))]
    if inv:
        state = ("Paid" if inv.status == "Paid"
                 else f"{fmt_money(inv.outstanding, currency=cur)} due {formatdate(inv.due_date)}")
        rows.append(("Latest invoice", f"{inv.name}: {fmt_money(inv.total, currency=cur)}, {state}"))
    return rows, (inv.name if inv and inv.status != "Paid" else None)


def _message(tenant, site, user, link, hours):
    from stemic_control.communications import email_html, how_to_pay, link as a

    url = f"https://{site}"
    school = escape_html(tenant.school_name or tenant.name)
    billing_rows, unpaid = _billing(tenant)
    pay_title, pay_body = how_to_pay(unpaid)
    return email_html(
        f"Welcome to Stemic Schools", f"<b>{school}</b> is ready. Here is everything you need to get started.",
        [("Your school's address", a(url)), ("Your username", user), *billing_rows],
        button=("Set your password", link),
        blocks=[("Getting started", "<ol style=\"margin:0;padding-left:20px\"><li>Click <b>Set your password</b> above.</li>"
                 f"<li>Sign in at {a(url)} with your username and new password.</li>"
                 "<li>Open <b>School Settings</b> to add your school's details and install your license key, "
                 "which we send separately.</li></ol>"),
                (pay_title, pay_body if unpaid else (pay_body and f"For renewals and future invoices: {pay_body}"))],
        note=f"The password link works once and expires in {hours} hours. If it has expired, reply to this email and "
             "we will send a new one. Questions? Just reply: we are here to help.")


def send(tenant_name):
    """Create the school's admin user (or a fresh link for it) and email the welcome. Returns who it went to."""
    tenant = frappe.get_doc("SaaS Tenant", tenant_name)
    if tenant.status != "Active" or not tenant.canonical_site:
        frappe.throw("The school's site is not ready yet", frappe.ValidationError)
    if not tenant.admin_email:
        frappe.throw("The school has no contact email", frappe.ValidationError)
    site = tenant.canonical_site
    data = _first_admin(site, tenant.admin_email, tenant.school_name and f"{tenant.school_name} Admin")
    subject = f"{tenant.school_name or tenant.name} is ready on Stemic Schools"
    frappe.sendmail(recipients=[tenant.admin_email], subject=subject,
                    message=_message(tenant, site, data["user"], data["link"], data.get("hours") or 24),
                    reference_doctype="SaaS Tenant", reference_name=tenant.name, now=True)
    frappe.db.set_value("SaaS Tenant", tenant.name, "welcome_sent_on", now_datetime(), update_modified=False)
    from stemic_control import communications

    communications._log(tenant.name, "Welcome", "Email", "Sent", tenant.admin_email, ("SaaS Tenant", tenant.name), subject)
    # the link stays in the email; the SMS only says where to look
    communications.deliver(tenant.name, "Welcome", ("SaaS Tenant", tenant.name), dedupe=False,
                           sms=f"Stemic Schools: {tenant.school_name or tenant.name} is ready at https://{site}. "
                               f"We emailed {tenant.admin_email} a link to set your password.")
    communications.tell_admins("Welcome", f"{tenant.school_name or tenant.name} is ready at https://{site}; welcome sent to "
                                          f"{tenant.admin_email}", "", ("SaaS Tenant", tenant.name), tenant.name, dedupe=False)
    return {"to": tenant.admin_email, "user": data["user"], "site": site}


def after_provisioning(tenant_name):
    """Called when a build succeeds. A failure to send never undoes the build: the platform admins are told instead."""
    from stemic_control import communications

    if not communications.wanted("Welcome"):
        return {"skipped": "Site ready (welcome) is off in Stemic Settings > Communications"}
    try:
        result = send(tenant_name)
        frappe.db.commit()
        return result
    except Exception as exc:
        frappe.db.rollback()
        reason = str(exc).splitlines()[0][:300] if str(exc) else exc.__class__.__name__
        log = frappe.log_error(title=f"Welcome email not sent for {tenant_name}", message=frappe.get_traceback())
        from stemic_control.alerts import notify_admins

        notify_admins(f"The welcome email for {tenant_name} was not sent",
                      escape_html(reason) + "<br>Open the school and use Send Welcome Email to try again.",
                      "SaaS Tenant", tenant_name)
        frappe.db.commit()
        return {"error": reason, "log": log.name if log else None}


@frappe.whitelist(methods=["POST"])
def resend(tenant):
    """Send the welcome again, with a fresh set-password link (platform admins only)."""
    from stemic_control.billing import _admin

    _admin()
    frappe.get_doc("SaaS Tenant", tenant).check_permission("write")
    return send(tenant)
