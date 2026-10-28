"""Tenant-local delivery audit and bounded retries.

Accepted means handed to provider/email queue, not confirmed delivery.
An interrupted Sending attempt remains ambiguous and must be reconciled.
"""
import hashlib
import json

import frappe
from frappe.utils import add_to_date, now_datetime

DOCTYPE = "School Notification Delivery"
MAX_ATTEMPTS = 3


def delivery_key(event_id, channel, recipient):
    return hashlib.sha256(
        json.dumps([event_id, channel, recipient], separators=(",", ":")).encode()
    ).hexdigest()


def queue_delivery(event_id, channel, recipient, message, subject=None,
                   reference_doctype=None, reference_name=None):
    """Durably deduplicate by event/channel/recipient. Call inside a DB transaction."""
    if channel not in ("SMS", "Email"):
        frappe.throw("Invalid channel")
    if not event_id or not recipient or not message:
        frappe.throw("Event ID, recipient and message required")
    key = delivery_key(event_id, channel, recipient)
    existing = frappe.db.get_value(DOCTYPE, {"idempotency_key": key}, "name")
    if existing:
        return existing
    try:
        doc = frappe.get_doc({
            "doctype": DOCTYPE, "idempotency_key": key, "channel": channel,
            "recipient": recipient, "message": message, "subject": subject,
            "status": "Queued", "reference_doctype": reference_doctype,
            "reference_name": reference_name,
        })
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        return frappe.db.get_value(DOCTYPE, {"idempotency_key": key}, "name")
    frappe.enqueue(
        "school_erp.api.notification_delivery.process_delivery",
        name=doc.name, queue="short", enqueue_after_commit=True,
    )
    return doc.name


def process_delivery(name):
    """Lock and claim, commit before external I/O to prevent concurrent sends."""
    rows = frappe.db.sql(
        """SELECT status, attempts FROM `tabSchool Notification Delivery`
           WHERE name=%s FOR UPDATE""", name, as_dict=True,
    )
    if not rows or rows[0].status not in ("Queued", "Retrying"):
        return
    attempt = int(rows[0].attempts or 0) + 1
    if attempt > MAX_ATTEMPTS:
        return
    frappe.db.set_value(DOCTYPE, name, {"status": "Sending", "attempts": attempt})
    frappe.db.commit()  # intentional: durable claim before calling provider
    doc = frappe.get_doc(DOCTYPE, name)
    settings = frappe.get_cached_doc("School Settings")
    enabled = settings.get(
        "enable_sms_notifications" if doc.channel == "SMS" else "enable_email_notifications", 1
    )
    if not enabled:
        frappe.db.set_value(DOCTYPE, name, "status", "Skipped")
        return
    try:
        if doc.channel == "SMS":
            from school_erp.api.communication_policy import reserve_sms
            if not reserve_sms(settings):
                frappe.db.set_value(DOCTYPE, name, {"status": "Skipped", "provider_response": "School SMS attempt budget exceeded"})
                return
            from school_erp.api.messaging import send_sms
            result = send_sms([doc.recipient], doc.message)
            if result.get("skipped"):
                frappe.db.set_value(DOCTYPE, name, "status", "Skipped")
                return
            if not result.get("sent"):
                raise RuntimeError("SMS provider did not accept recipient")
        else:
            frappe.sendmail(
                recipients=[doc.recipient], subject=doc.subject or "School Notification",
                message=doc.message, now=False,
                reference_doctype=doc.reference_doctype or None,
                reference_name=doc.reference_name or None,
            )
        frappe.db.set_value(DOCTYPE, name, {
            "status": "Accepted",
            "provider_response": "Accepted by sender/queue; delivery not verified",
        })
    except Exception as exc:
        retry = attempt < MAX_ATTEMPTS
        frappe.db.set_value(DOCTYPE, name, {
            "status": "Retrying" if retry else "Failed",
            "provider_response": str(exc)[:500],
            "next_attempt_at": add_to_date(now_datetime(), minutes=2 ** attempt) if retry else None,
        })


def retry_due():
    """Queue due retries. Never automatically resend ambiguous 'Sending' jobs."""
    names = frappe.get_all(
        DOCTYPE, filters={"status": "Retrying", "next_attempt_at": ("<=", now_datetime())},
        pluck="name", limit_page_length=100,
    )
    for name in names:
        frappe.enqueue(
            "school_erp.api.notification_delivery.process_delivery",
            name=name, queue="short", enqueue_after_commit=True,
        )
