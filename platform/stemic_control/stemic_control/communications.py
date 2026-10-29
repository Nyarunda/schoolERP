"""Everything Stemic tells a school: site ready, invoices, receipts, overdue reminders, license keys, suspension.

By email (the default outgoing Email Account, to the school's contact email) and, when SMS is on in Stemic Settings >
Communications, by SMS to the contact phone through any HTTP gateway (school_erp.api.sms_gateway, the same sender
schools use). Links and license keys go by email only; the SMS points to it.

Messages are sent after the record that caused them is committed (an invoice that rolled back is never announced),
in the background, and never block billing. Each message and channel is recorded as a SaaS Communication (Sent,
Failed with the reason, or Skipped with the reason), which also stops the same event being sent twice.
"""

import frappe
from frappe.utils import escape_html, fmt_money, formatdate, now_datetime

EVENTS = {  # event -> Stemic Settings switch
    "Welcome": "notify_welcome", "Invoice Issued": "notify_invoice", "Payment Received": "notify_payment",
    "Invoice Overdue": "notify_overdue", "License Issued": "notify_license", "Suspended": "notify_status",
    "Resumed": "notify_status",
}


def _settings():
    return frappe.get_cached_doc("Stemic Settings")


def wanted(event):
    switch = _settings().get(EVENTS[event])
    return switch is None or bool(int(switch))  # a switch not saved yet counts as on


# ----------------------------------------------------------------------------- SMS through the platform gateway
def sms_on():
    s = _settings()
    return bool(s.get("notify_schools_by_sms") and s.get("sms_url") and s.get("sms_recipient_param") and s.get("sms_message_param"))


def _gateway():
    """A gateway object for school_erp.api.sms_gateway.send, built from Stemic Settings."""
    from frappe.utils.password import get_decrypted_password

    s = _settings()
    rows = []
    for line in (s.get("sms_parameters") or "").splitlines():
        header = line.strip().lower().startswith("header:")
        name, sep, value = line.strip()[7 if header else 0:].partition("=")
        if sep and name.strip():
            rows.append(frappe._dict(parameter=name.strip(), value=value.strip(), is_header=int(header)))
    key = get_decrypted_password("Stemic Settings", "Stemic Settings", "sms_api_key", raise_exception=False)
    return frappe._dict(
        name="Stemic Settings SMS", enabled=1, url=s.sms_url, http_method=s.sms_http_method or "POST",
        body_format=s.sms_body_format or "JSON", recipient_param=s.sms_recipient_param, message_param=s.sms_message_param,
        number_format=s.sms_number_format or "2547XXXXXXXX", recipients_mode="One request per number", recipient_separator=",",
        sender_param=s.sms_sender_param, sender_id=s.sms_sender_id, api_key_param=s.sms_api_key_param,
        api_key_in=s.sms_api_key_in or "Body", api_key_prefix=s.sms_api_key_prefix, parameters=rows,
        success_field=s.sms_success_field, success_values=s.sms_success_values, success_text=s.sms_success_text,
        timeout=20, get_password=lambda field, raise_exception=False: key)


def send_sms(phone, message):
    """(ok, detail) for one SMS from the platform gateway."""
    try:
        from school_erp.api import sms_gateway
        from school_erp.logic.text import normalize_phone
    except ImportError:
        return False, "SMS needs School ERP's code on this bench"
    cc = _settings().get("sms_country_code") or "254"
    number = normalize_phone(phone, cc)
    if not number:
        return False, f"{phone} is not a phone number"
    result = sms_gateway.send(_gateway(), [number], message, country_code=cc)
    return bool(result["sent"]), "; ".join(result["errors"])


@frappe.whitelist(methods=["POST"])
def send_test_sms(number=None):
    from stemic_control.billing import _admin

    _admin()
    if not sms_on():
        frappe.throw("Switch on SMS schools and fill in the gateway first", frappe.ValidationError)
    ok, detail = send_sms(number or _settings().get("sms_test_number"), "Test from Stemic Schools: SMS to schools works.")
    return {"sent": ok, "error": detail}


def check_gateway_url(settings):
    """Stemic Settings.validate: the gateway URL must be https to a public address (same rule schools have)."""
    if settings.get("notify_schools_by_sms") and settings.get("sms_url"):
        from school_erp.api.sms_gateway import check_url

        check_url(settings.sms_url)


# ----------------------------------------------------------------------------- the record of what was sent
def _log(tenant, event, channel, status, recipient=None, reference=(None, None), subject=None, detail=None, key=None):
    doc = frappe.get_doc({"doctype": "SaaS Communication", "tenant": tenant, "event": event, "channel": channel,
                          "status": status, "recipient": recipient, "reference_doctype": reference[0],
                          "reference_name": reference[1], "subject": subject, "detail": (detail or "")[:1000],
                          "sent_on": now_datetime(), "dedupe_key": key})
    doc.flags.from_notify = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _already_sent(key):
    return bool(key and frappe.db.exists("SaaS Communication", {"dedupe_key": key, "status": "Sent"}))


def deliver(tenant, event, reference=(None, None), email=None, sms=None, dedupe=True):
    """Send one event to a school by every channel that is on. `email` is (subject, html); `sms` is text."""
    if not wanted(event):
        return []
    t = frappe.db.get_value("SaaS Tenant", tenant, ["admin_email", "contact_phone"], as_dict=True) or frappe._dict()
    out = []
    if email and _settings().get("notify_schools_by_email") not in (0, "0"):
        key = f"{event}|{reference[0]}|{reference[1]}|Email" if dedupe and reference[1] else None
        if not _already_sent(key):
            subject, html = email
            if not t.admin_email:
                out.append(_log(tenant, event, "Email", "Skipped", None, reference, subject, "The school has no contact email"))
            else:
                try:
                    frappe.sendmail(recipients=[t.admin_email], subject=subject, message=html, reference_doctype="SaaS Tenant",
                                    reference_name=tenant)
                    out.append(_log(tenant, event, "Email", "Sent", t.admin_email, reference, subject, key=key))
                except Exception as exc:
                    out.append(_log(tenant, event, "Email", "Failed", t.admin_email, reference, subject, str(exc)))
    if sms and sms_on():
        key = f"{event}|{reference[0]}|{reference[1]}|SMS" if dedupe and reference[1] else None
        if not _already_sent(key):
            if not t.contact_phone:
                out.append(_log(tenant, event, "SMS", "Skipped", None, reference, None, "The school has no contact phone"))
            else:
                try:
                    ok, detail = send_sms(t.contact_phone, sms)
                except Exception as exc:
                    ok, detail = False, str(exc)
                out.append(_log(tenant, event, "SMS", "Sent" if ok else "Failed", t.contact_phone, reference, None,
                                None if ok else detail, key=key if ok else None))
    return out


def queue(event, **kwargs):
    """Send `event` once the current transaction commits, in the background."""
    if not wanted(event):
        return
    frappe.enqueue("stemic_control.communications.send_event", queue="short", enqueue_after_commit=True,
                   event=event, **kwargs)


# ----------------------------------------------------------------------------- the messages
def _money(amount, currency):
    return fmt_money(amount, currency=currency or "KES")


def _instructions(invoice):
    from stemic_control.billing import settings

    return (settings().payment_instructions or "").replace("{invoice}", invoice)


def _email(title, lines, footer=""):
    rows = "".join(f"<tr><td>{escape_html(k)}</td><td><b>{escape_html(str(v))}</b></td></tr>" for k, v in lines if v not in (None, ""))
    return f"<p>{title}</p><table cellpadding=\"4\">{rows}</table>{footer}<p>Stemic Schools</p>"


def send_event(event, **kw):
    """Background job: build the event's messages from the records as committed now, and deliver them."""
    if event in ("Invoice Issued", "Invoice Overdue"):
        inv = frappe.get_doc("SaaS Invoice", kw["invoice"])
        school, total = inv.school_name or inv.tenant, _money(inv.outstanding if event == "Invoice Overdue" else inv.total, inv.currency)
        pay = _instructions(inv.name)
        due = formatdate(inv.due_date)
        if event == "Invoice Issued":
            subject = f"Invoice {inv.name} from Stemic Schools: {total} due {due}"
            title = f"Here is the invoice for <b>{escape_html(school)}</b>'s Stemic Schools subscription."
            sms = f"Stemic Schools: invoice {inv.name} for {school}, {total}, due {due}. {pay}".strip()
        else:
            subject = f"Overdue: invoice {inv.name}, {total}"
            title = f"Invoice {inv.name} for <b>{escape_html(school)}</b> was due on {due} and is not fully paid yet."
            sms = f"Stemic Schools: invoice {inv.name} ({total}) was due {due}. Please pay to keep {school} running. {pay}".strip()
        html = _email(title, [("Invoice", inv.name), ("Plan", inv.plan),
                              ("Period", f"{formatdate(inv.period_start)} to {formatdate(inv.period_end)}"),
                              ("Amount due", total), ("Due date", due)],
                      f"<p><b>How to pay:</b> {escape_html(pay)}</p>" if pay else "")
        return deliver(inv.tenant, event, ("SaaS Invoice", inv.name), (subject, html), sms)

    if event == "Payment Received":
        pay = frappe.get_doc("SaaS Payment", kw["payment"])
        inv = frappe.db.get_value("SaaS Invoice", pay.invoice, ["outstanding", "currency", "school_name", "subscription"], as_dict=True)
        ends = frappe.db.get_value("SaaS Subscription", inv.subscription, "ends_on")
        amount, balance = _money(pay.amount, inv.currency), _money(inv.outstanding, inv.currency)
        until = formatdate(ends) if ends else None
        subject = f"Payment received: {amount} for {pay.invoice}"
        html = _email(f"Thank you. We received your payment for <b>{escape_html(inv.school_name or pay.tenant)}</b>.",
                      [("Amount", amount), ("Reference", pay.reference), ("Invoice", pay.invoice), ("Balance", balance),
                       ("Subscription active until", until)])
        sms = f"Stemic Schools: received {amount} ({pay.reference}) for {pay.invoice}. Balance {balance}." + (
            f" Active until {until}." if until else "")
        return deliver(pay.tenant, event, ("SaaS Payment", pay.name), (subject, html), sms)

    if event == "License Issued":
        lic = frappe.get_doc("SaaS License", kw["license"])
        subject = f"Your Stemic Schools license key for {lic.school_name or lic.tenant}"
        html = _email(f"Your license for <b>{escape_html(lic.school_name or lic.tenant)}</b> is ready.",
                      [("School site", f"https://{lic.site}"), ("Plan", lic.plan), ("Modules", (lic.modules or "").replace("\n", ", ")),
                       ("Valid until", formatdate(lic.expires_on) if lic.expires_on else "No end date")],
                      "<p>Sign in to your school's site, open <b>School Settings</b>, click <b>Install Key</b> and paste:</p>"
                      f"<pre style=\"white-space:pre-wrap;word-break:break-all;background:#f5f5f5;padding:10px\">{escape_html(lic.signed_key)}</pre>")
        sms = f"Stemic Schools: your license for {lic.school_name or lic.tenant} is ready. The key is in your email."
        return deliver(lic.tenant, event, ("SaaS License", lic.name), (subject, html), sms)

    if event in ("Suspended", "Resumed"):
        tenant = kw["tenant"]
        school = frappe.db.get_value("SaaS Tenant", tenant, "school_name") or tenant
        if event == "Suspended":
            subject, line = f"{school} is suspended on Stemic Schools", f"<b>{escape_html(school)}</b>'s Stemic Schools service is suspended."
            sms = f"Stemic Schools: {school}'s service is suspended. Contact us to restore it."
        else:
            subject, line = f"{school} is active again on Stemic Schools", f"<b>{escape_html(school)}</b>'s Stemic Schools service is active again."
            sms = f"Stemic Schools: {school}'s service is active again."
        # a school can be suspended and resumed more than once: each change is its own message
        return deliver(tenant, event, ("SaaS Tenant", tenant), (subject, _email(line, [])), sms, dedupe=False)
    frappe.throw(f"Unknown school communication {event}")
