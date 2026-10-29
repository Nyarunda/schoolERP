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


def _message(tenant, site, user, link, hours):
    url = f"https://{site}"
    school = escape_html(tenant.school_name or tenant.name)
    return f"""<p>Hello,</p>
<p><b>{school}</b> is ready on Stemic Schools.</p>
<table cellpadding="4">
  <tr><td>Your school's address</td><td><a href="{url}">{url}</a></td></tr>
  <tr><td>Your username</td><td><b>{escape_html(user)}</b></td></tr>
</table>
<p><a href="{escape_html(link)}" style="display:inline-block;padding:10px 18px;background:#171717;color:#fff;
text-decoration:none;border-radius:6px">Set your password</a></p>
<p>This link works once and expires in {hours} hours. If it has expired, reply to this email and we will send a new
one. Then sign in at <a href="{url}">{url}</a> with your username and the password you chose.</p>
<p>After signing in, open <b>School Settings</b> to add your school's details and install your license key.</p>
<p>Welcome aboard,<br>Stemic Schools</p>"""


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
