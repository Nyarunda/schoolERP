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
    "Resumed": "notify_status", "School Registered": "notify_registered", "Trial Ending": "trial_reminder",
}
ADMIN_ONLY = {"School Registered"}
# RFC 2606 / 6761 names that never belong to a real school: tests and scripts use them, so nothing is ever sent there
RESERVED = (".test", ".example", ".invalid", ".localhost", "@example.com", "@example.org", "@example.net")


def _settings():
    return frappe.get_cached_doc("Stemic Settings")


def _on(value):
    return value is None or bool(int(value or 0))  # a switch not saved yet counts as on


def wanted(event):
    return _on(_settings().get(EVENTS[event]))


def _reserved(address):
    return (address or "").strip().lower().endswith(RESERVED)


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
def _log(tenant, event, channel, status, recipient=None, reference=(None, None), subject=None, detail=None, key=None,
         audience="School"):
    doc = frappe.get_doc({"doctype": "SaaS Communication", "tenant": tenant, "event": event, "channel": channel,
                          "audience": audience,
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
            elif _reserved(t.admin_email):
                out.append(_log(tenant, event, "Email", "Skipped", t.admin_email, reference, subject, "A reserved test address"))
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
    if frappe.flags.in_test and not frappe.flags.stemic_comms_in_tests:
        return  # a test that commits must not leave real messages queued for the worker
    frappe.enqueue("stemic_control.communications.send_event", queue="short", enqueue_after_commit=True,
                   event=event, **kwargs)


# ----------------------------------------------------------------------------- platform admins
def _admin_phones():
    from stemic_control.alerts import platform_admins

    users = platform_admins()
    if not users:
        return []
    return frappe.get_all("User", filters={"name": ("in", users), "mobile_no": ("is", "set")}, fields=["name", "mobile_no"])


def sms_admins(event, text, reference=(None, None), tenant=None, key=None):
    """SMS every platform admin with a mobile number, when SMS is on (and admin SMS is). Once per key and admin."""
    s = _settings()
    if not (sms_on() and _on(s.get("notify_admins_by_sms"))):
        return []
    out = []
    for admin in _admin_phones():
        k = f"{key}|{admin.name}" if key else None
        if _already_sent(k):
            continue
        try:
            ok, detail = send_sms(admin.mobile_no, text)
        except Exception as exc:
            ok, detail = False, str(exc)
        out.append(_log(tenant, event, "SMS", "Sent" if ok else "Failed", admin.mobile_no, reference, None,
                        None if ok else detail, key=k if ok else None, audience="Platform admins"))
    return out


def tell_admins(event, title, description="", reference=(None, None), tenant=None, dedupe=True):
    """A short summary of a school event for every platform admin: bell and email (alerts.notify_admins), and SMS."""
    if not (wanted(event) and _on(_settings().get("notify_admins_copy"))):
        return
    from stemic_control.alerts import notify_admins

    notify_admins(title, description, reference[0], reference[1], sms=False)
    key = f"admin|{event}|{reference[0]}|{reference[1]}" if dedupe and reference[1] else None
    sms_admins(event, f"Stemic: {title}", reference, tenant, key)


# ----------------------------------------------------------------------------- the messages
def _money(amount, currency):
    """KES 114,000.00: the currency code, as on the invoice (Frappe's symbol for KES is "Sh")."""
    return f"{currency or 'KES'} {fmt_money(amount or 0, precision=2)}"


def _instructions(invoice):
    from stemic_control.billing import settings

    return (settings().payment_instructions or "").replace("{invoice}", invoice)


INK, MUTED, LINE = "#14243d", "#5b6b82", "#e6ebf2"
FONT = "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def brand():
    """Stemic Settings > Communications > Branding, with Stemic's own defaults."""
    s = _settings()
    email = s.get("support_email") or frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1},
                                                          "email_id") or "support@stemicschools.com"
    return frappe._dict(name=(s.get("brand_name") or "Stemic Schools").strip(), color=s.get("brand_color") or "#1b3a6b",
                        accent=s.get("accent_color") or "#43a047", email=email, phone=s.get("support_phone") or "")


class Html(str):
    """A table value that is already HTML (a link): shown as is. Everything else is escaped."""


def link(url, text=None):
    return Html(f'<a href="{escape_html(url)}" style="color:{brand().color};font-weight:600">{escape_html(text or url)}</a>')


def email_html(heading, intro="", rows=(), button=None, blocks=(), note=""):
    """The email layout: a header band in the brand colour, the heading, a short intro (HTML), a details table, an
    optional button (label, url), boxed sections (title, HTML), and a closing note. The Email Account footer follows."""
    b = brand()

    def value(v):
        return v if isinstance(v, Html) else escape_html(str(v))

    table = "".join(
        f'<tr><td style="padding:9px 14px;color:{MUTED};border-bottom:1px solid {LINE};width:40%;vertical-align:top">'
        f'{escape_html(k)}</td><td style="padding:9px 14px;color:{INK};font-weight:600;border-bottom:1px solid {LINE}">'
        f'{value(v)}</td></tr>' for k, v in rows if v not in (None, ""))
    table = (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid {LINE};'
             f'border-radius:8px;border-collapse:separate;margin:18px 0;font-size:14px">{table}</table>') if table else ""
    cta = (f'<p style="margin:22px 0"><a href="{escape_html(button[1])}" style="display:inline-block;background:{b.accent};'
           f'color:#ffffff;padding:13px 28px;border-radius:6px;font-weight:700;font-size:15px;text-decoration:none">'
           f'{escape_html(button[0])}</a></p>') if button else ""
    boxes = "".join(
        f'<div style="background:#f6f8fa;border-left:4px solid {b.accent};border-radius:6px;padding:14px 16px;margin:16px 0">'
        f'<div style="font-weight:700;color:{INK};margin-bottom:6px">{escape_html(title)}</div>'
        f'<div style="color:{INK};font-size:14px;line-height:1.55">{body}</div></div>' for title, body in blocks if body)
    closing = f'<p style="color:{MUTED};font-size:13px;line-height:1.55;margin:18px 0 0">{note}</p>' if note else ""
    first, _, rest = b.name.partition(" ")
    title = escape_html(first) + (f' <span style="opacity:.75">{escape_html(rest)}</span>' if rest else "")
    return (f'<div style="background:#f4f7fb;padding:24px 8px;{FONT}">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;margin:0 auto;'
            f'background:#ffffff;border:1px solid #e1e7f0;border-radius:10px;overflow:hidden">'
            f'<tr><td style="background:{b.color};padding:16px 28px;font-size:19px;font-weight:700;color:#ffffff">{title}</td></tr>'
            f'<tr><td style="padding:26px 28px 30px;color:{INK};font-size:15px;line-height:1.55">'
            f'<h1 style="font-size:22px;line-height:1.3;color:{INK};margin:0 0 10px">{escape_html(heading)}</h1>'
            f'{f"<p style=margin:0>{intro}</p>" if intro else ""}{table}{cta}{boxes}{closing}'
            f'</td></tr></table></div>')


def how_to_pay(invoice=None):
    """The 'How to pay' box: Stemic Settings > Billing > Payment instructions, with {invoice} filled in."""
    text = _instructions(invoice or "your invoice number")
    return ("How to pay", escape_html(text).replace("\n", "<br>")) if text.strip() else ("How to pay", "")


def _contact():
    b = brand()
    return "Questions? Reply to this email" + (f" or call {escape_html(b.phone)}" if b.phone else "") + "."


# ----------------------------------------------------------------------------- what each message says
# Each builder takes plain values (records, or samples for the preview) and returns (subject, html, sms).
def render_invoice(event, inv):
    b = brand()
    school = inv.school_name or inv.tenant
    total = _money(inv.outstanding if event == "Invoice Overdue" else inv.total, inv.currency)
    pay, due = _instructions(inv.name), formatdate(inv.due_date)
    if event == "Invoice Issued":
        subject = f"Invoice {inv.name} from {b.name}: {total} due {due}"
        intro = f"Here is the invoice for <b>{escape_html(school)}</b>'s {escape_html(b.name)} subscription."
        sms = f"{b.name}: invoice {inv.name} for {school}, {total}, due {due}. {pay}".strip()
    else:
        subject = f"Overdue: invoice {inv.name}, {total}"
        intro = f"Invoice {inv.name} for <b>{escape_html(school)}</b> was due on {due} and is not fully paid yet."
        sms = f"{b.name}: invoice {inv.name} ({total}) was due {due}. Please pay to keep {school} running. {pay}".strip()
    html = email_html("Invoice " + inv.name if event == "Invoice Issued" else "Payment overdue", intro,
                      [("Invoice", inv.name), ("School", school), ("Plan", inv.plan),
                       ("Period", f"{formatdate(inv.period_start)} to {formatdate(inv.period_end)}"),
                       ("Amount", _money(inv.total, inv.currency)),
                       ("Discount", _money(inv.discount_amount, inv.currency) if inv.discount_amount else None),
                       ("Amount due", total), ("Due date", due)],
                      blocks=[how_to_pay(inv.name)],
                      note="Use the invoice number as the payment reference, so your payment is matched at once. " + _contact())
    return subject, html, sms


def render_payment(pay, inv, ends_on):
    b = brand()
    amount, balance = _money(pay.amount, inv.currency), _money(inv.outstanding, inv.currency)
    until = formatdate(ends_on) if ends_on else None
    subject = f"Payment received: {amount} for {pay.invoice}"
    html = email_html("Payment received", f"Thank you. We received your payment for <b>{escape_html(inv.school_name or pay.tenant)}</b>.",
                      [("Amount", amount), ("Paid by", pay.mode), ("Reference", pay.reference),
                       ("Date", formatdate(pay.payment_date)), ("Invoice", pay.invoice), ("Balance", balance),
                       ("Subscription active until", until)],
                      blocks=[how_to_pay(pay.invoice)] if inv.outstanding else [],
                      note="Keep this email as your receipt. " + _contact())
    sms = f"{b.name}: received {amount} ({pay.reference}) for {pay.invoice}. Balance {balance}." + (
        f" Active until {until}." if until else "")
    return subject, html, sms


def render_license(lic):
    from stemic_control.domains import public_host

    b = brand()
    school = lic.school_name or lic.tenant
    url = f"https://{(lic.tenant and public_host(lic.tenant)) or lic.site}"
    subject = f"Your {b.name} license key for {school}"
    html = email_html("Your license key", f"The license for <b>{escape_html(school)}</b> is ready.",
                      [("School site", link(url)), ("Plan", lic.plan),
                       ("Modules", (lic.modules or "").replace("\n", ", ")),
                       ("Valid until", formatdate(lic.expires_on) if lic.expires_on else "No end date")],
                      button=("Open your school", url),
                      blocks=[("Install it", "Sign in to your school, open <b>School Settings</b>, click <b>Install Key</b> "
                               "and paste the key below.<pre style=\"white-space:pre-wrap;word-break:break-all;background:#ffffff;"
                               f"border:1px solid {LINE};border-radius:6px;padding:10px;margin:10px 0 0;font-size:12px\">"
                               f"{escape_html(lic.signed_key)}</pre>")],
                      note="Keep this key private: it unlocks your plan's modules for your school's site only.")
    sms = f"{b.name}: your license for {school} is ready. The key is in your email."
    return subject, html, sms


def render_status(event, school):
    b = brand()
    if event == "Suspended":
        subject = f"{school} is suspended on {b.name}"
        line = f"<b>{escape_html(school)}</b>'s {escape_html(b.name)} service is suspended."
        sms = f"{b.name}: {school}'s service is suspended. Contact us to restore it."
    else:
        subject = f"{school} is active again on {b.name}"
        line = f"<b>{escape_html(school)}</b>'s {escape_html(b.name)} service is active again."
        sms = f"{b.name}: {school}'s service is active again."
    html = email_html("Service suspended" if event == "Suspended" else "Service active again", line,
                      blocks=[how_to_pay()] if event == "Suspended" else [],
                      note=_contact() if event == "Suspended" else "Thank you for staying with us.")
    return subject, html, sms


def render_trial_ending(sub, invoice=None):
    """A few days before a free trial ends: what happens next and how to keep the school's site."""
    b = brand()
    school = sub.school_name or sub.tenant
    ends = formatdate(sub.ends_on)
    subject = f"{school}'s free trial of {b.name} ends on {ends}"
    rows = [("School", school), ("Plan", sub.plan), ("Trial ends", ends)]
    if invoice:
        rows += [("Invoice", invoice.name), ("Amount", _money(invoice.outstanding, invoice.currency)),
                 ("Due", formatdate(invoice.due_date))]
    html = email_html("Your free trial is ending", f"<b>{escape_html(school)}</b>'s free trial of {escape_html(b.name)} "
                      f"ends on <b>{ends}</b>. To keep using it without a break, pay for your plan before then.", rows,
                      blocks=[how_to_pay(invoice.name if invoice else None)], note=_contact())
    pay = f" {_instructions(invoice.name)}" if invoice and _instructions(invoice.name) else ""
    sms = f"{b.name}: {school}'s free trial ends {ends}. Pay for your plan to keep using it.{pay}".strip()
    return subject, html, sms


def send_event(event, **kw):
    """Background job: build the event's messages from the records as committed now, and deliver them."""
    if event in ("Invoice Issued", "Invoice Overdue"):
        inv = frappe.get_doc("SaaS Invoice", kw["invoice"])
        subject, html, sms = render_invoice(event, inv)
        out = deliver(inv.tenant, event, ("SaaS Invoice", inv.name), (subject, html), sms)
        total = _money(inv.outstanding if event == "Invoice Overdue" else inv.total, inv.currency)
        what = "issued to" if event == "Invoice Issued" else "overdue for"
        tell_admins(event, f"Invoice {inv.name} {what} {inv.school_name or inv.tenant}: {total}, due {formatdate(inv.due_date)}",
                    "", ("SaaS Invoice", inv.name), inv.tenant)
        return out

    if event == "Payment Received":
        pay = frappe.get_doc("SaaS Payment", kw["payment"])
        inv = frappe.db.get_value("SaaS Invoice", pay.invoice, ["outstanding", "currency", "school_name", "subscription"], as_dict=True)
        ends = frappe.db.get_value("SaaS Subscription", inv.subscription, "ends_on")
        subject, html, sms = render_payment(pay, inv, ends)
        out = deliver(pay.tenant, event, ("SaaS Payment", pay.name), (subject, html), sms)
        tell_admins(event, f"Payment {_money(pay.amount, inv.currency)} received from {inv.school_name or pay.tenant} for "
                           f"{pay.invoice} ({pay.mode} {pay.reference}); balance {_money(inv.outstanding, inv.currency)}",
                    "", ("SaaS Payment", pay.name), pay.tenant)
        return out

    if event == "License Issued":
        lic = frappe.get_doc("SaaS License", kw["license"])
        subject, html, sms = render_license(lic)
        out = deliver(lic.tenant, event, ("SaaS License", lic.name), (subject, html), sms)
        tell_admins(event, f"License {lic.name} issued to {lic.school_name or lic.tenant} ({lic.plan})", "",
                    ("SaaS License", lic.name), lic.tenant)
        return out

    if event in ("Suspended", "Resumed"):
        tenant = kw["tenant"]
        school = frappe.db.get_value("SaaS Tenant", tenant, "school_name") or tenant
        subject, html, sms = render_status(event, school)
        # a school can be suspended and resumed more than once: each change is its own message
        out = deliver(tenant, event, ("SaaS Tenant", tenant), (subject, html), sms, dedupe=False)
        tell_admins(event, f"{school} was {event.lower()}", "", ("SaaS Tenant", tenant), tenant, dedupe=False)
        return out

    if event == "Trial Ending":
        sub = frappe.get_doc("SaaS Subscription", kw["subscription"])
        from stemic_control.billing import OPEN

        inv_name = frappe.db.get_value("SaaS Invoice", {"subscription": sub.name, "docstatus": 1, "status": ("in", OPEN)}, "name")
        inv = frappe.get_doc("SaaS Invoice", inv_name) if inv_name else None
        subject, html, sms = render_trial_ending(sub, inv)
        out = deliver(sub.tenant, event, ("SaaS Subscription", sub.name), (subject, html), sms)
        tell_admins(event, f"{sub.school_name or sub.tenant}'s free trial ends {formatdate(sub.ends_on)}", "",
                    ("SaaS Subscription", sub.name), sub.tenant)
        return out

    if event == "School Registered":  # platform admins only
        t = frappe.db.get_value("SaaS Tenant", kw["tenant"], ["school_name", "admin_email", "contact_phone", "agent"], as_dict=True)
        extra = ", ".join(x for x in (t.admin_email, t.contact_phone, t.agent and f"agent {t.agent}") if x)
        return tell_admins(event, f"New school registered: {t.school_name} ({kw['tenant']})" + (f", {extra}" if extra else ""),
                           "", ("SaaS Tenant", kw["tenant"]), kw["tenant"])
    frappe.throw(f"Unknown school communication {event}")


# ----------------------------------------------------------------------------- preview (Stemic Settings)
PREVIEWS = ["Welcome", "Invoice Issued", "Payment Received", "Invoice Overdue", "License Issued", "Trial Ending", "Suspended"]


@frappe.whitelist(methods=["GET"])
def preview(event="Welcome"):
    """One email and its SMS with sample data, laid out as sent: the current branding, payment instructions and the
    default Email Account's footer. Nothing is sent."""
    from frappe.utils import add_days, add_months, nowdate

    from stemic_control.billing import _admin

    _admin()
    if event not in PREVIEWS:
        frappe.throw(f"No preview for {event}", frappe.ValidationError)
    today, number = nowdate(), "SINV-2026-00012"
    inv = frappe._dict(name=number, tenant="greenfield", school_name="Greenfield Academy", plan="Standard",
                       period_start=today, period_end=add_days(add_months(today, 12), -1), total=114000, discount_amount=0,
                       outstanding=114000, currency="KES", due_date=add_days(today, 14))
    if event == "Welcome":
        from stemic_control import welcome

        rows = [("Plan", "Standard (KES 9,500.00 a month)"), ("Subscription", "Active, paid until " + formatdate(inv.period_end)),
                ("Latest invoice", f"{number}: KES 114,000.00, KES 114,000.00 due {formatdate(inv.due_date)}")]
        site = f"greenfield.{frappe.conf.get('stemic_site_domain') or 'stemicschools.com'}"
        html = welcome.render(inv.school_name, site, "head@greenfield.ac.ke", f"https://{site}/update-password?key=sample",
                              24, rows, number)
        subject = f"{inv.school_name} is ready on {brand().name}"
        sms = welcome.sms_text(inv.school_name, site, "head@greenfield.ac.ke")
    elif event in ("Invoice Issued", "Invoice Overdue"):
        subject, html, sms = render_invoice(event, inv)
    elif event == "Payment Received":
        pay = frappe._dict(amount=114000, mode="M-Pesa", reference="QAB12CD34E", payment_date=today, invoice=number, tenant="greenfield")
        subject, html, sms = render_payment(pay, frappe._dict(inv, outstanding=0), inv.period_end)
    elif event == "License Issued":
        lic = frappe._dict(tenant="greenfield", school_name=inv.school_name, plan="Standard", site="greenfield.stemicschools.com",
                           modules="Fees\nMessaging\nM-Pesa\nTimetable\nStaff\nTransport", expires_on=inv.period_end,
                           signed_key="SAMPLE.eyJzY2hvb2wiOiJHcmVlbmZpZWxkIEFjYWRlbXkifQ.SIGNATURE")
        subject, html, sms = render_license(lic)
    elif event == "Trial Ending":
        sub = frappe._dict(name="SUB-00012", tenant="greenfield", school_name=inv.school_name, plan="Standard",
                           ends_on=add_days(today, 3))
        subject, html, sms = render_trial_ending(sub, frappe._dict(inv, due_date=add_days(today, 3)))
    else:
        subject, html, sms = render_status(event, inv.school_name)
    footer = frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "footer") or ""
    return {"subject": subject, "html": html + footer, "sms": sms, "events": PREVIEWS}
