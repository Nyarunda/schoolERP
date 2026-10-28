"""Tenant-local signed outbound webhooks. Explicit event allowlist, no automatic DocType subscription."""
import hashlib
import hmac
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import frappe
import requests
from frappe.utils import add_to_date, now_datetime

ENDPOINT = "School Webhook Endpoint"
DELIVERY = "School Webhook Delivery"
ALLOWED_EVENTS = {"student.created", "fee_payment.posted", "attendance.recorded", "invoice.submitted"}


def validate_target(url):
    parsed = urlsplit(url or "")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        frappe.throw("Webhook requires an HTTPS URL on port 443 without credentials")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        frappe.throw("Local webhook destinations are prohibited")
    try:
        addrs = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        frappe.throw("Webhook hostname could not be resolved")
    for item in addrs:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            frappe.throw("Webhook target resolves to a non-public address")
    return url


def sign(body, secret):
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def publish(event_id, event_type, payload):
    """Only explicit public event schemas; caller must enqueue after transaction commit."""
    if event_type not in ALLOWED_EVENTS:
        frappe.throw("Webhook event not supported")
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    endpoints = frappe.get_all(ENDPOINT, filters={"enabled": 1}, fields=["name", "event_types"])
    for ep in endpoints:
        if event_type not in (ep.event_types or "").splitlines():
            continue
        key = hashlib.sha256(f"{ep.name}:{event_id}:{event_type}".encode()).hexdigest()
        if frappe.db.exists(DELIVERY, key):
            continue
        try:
            frappe.get_doc({"doctype": DELIVERY, "name": key, "endpoint": ep.name,
                            "event_id": event_id, "event_type": event_type, "payload": data}).insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            continue
        frappe.enqueue("school_erp.api.webhooks.deliver", name=key, queue="short", enqueue_after_commit=True)


def deliver(name):
    rows = frappe.db.sql("SELECT status,attempts FROM `tabSchool Webhook Delivery` WHERE name=%s FOR UPDATE", name, as_dict=True)
    if not rows or rows[0].status not in ("Queued", "Retrying"):
        return
    attempt = int(rows[0].attempts or 0) + 1
    delivery = frappe.get_doc(DELIVERY, name)
    endpoint = frappe.get_doc(ENDPOINT, delivery.endpoint)
    cap = min(max(int(endpoint.max_attempts or 3), 1), 5)
    if attempt > cap:
        return
    frappe.db.set_value(DELIVERY, name, {"status": "Sending", "attempts": attempt})
    frappe.db.commit()
    if not endpoint.enabled:
        frappe.db.set_value(DELIVERY, name, {"status": "Failed", "error": "Endpoint disabled"})
        return
    try:
        url = validate_target(endpoint.endpoint_url)
        secret = endpoint.get_password("secret")
        body = delivery.payload
        # Disable redirects and environment proxies to reduce SSRF avenues.
        with requests.Session() as client:
            client.trust_env = False
            response = client.post(url, data=body.encode(), timeout=(5, 10), allow_redirects=False,
                                   headers={"Content-Type": "application/json",
                                            "X-Stemic-Event": delivery.event_type,
                                            "X-Stemic-Delivery": delivery.name,
                                            "X-Stemic-Signature-SHA256": sign(body, secret)})
        if 200 <= response.status_code < 300:
            frappe.db.set_value(DELIVERY, name, {"status": "Accepted", "response_code": response.status_code})
        else:
            raise RuntimeError(f"HTTP {response.status_code}")
    except Exception as exc:
        again = attempt < cap
        frappe.db.set_value(DELIVERY, name, {"status": "Retrying" if again else "Failed",
                          "error": str(exc)[:300],
                          "next_attempt_at": add_to_date(now_datetime(), minutes=2**attempt) if again else None})


def retry_due():
    names = frappe.get_all(DELIVERY, filters={"status": "Retrying", "next_attempt_at": ("<=", now_datetime())},
                           pluck="name", limit_page_length=100)
    for name in names:
        frappe.enqueue("school_erp.api.webhooks.deliver", name=name, queue="short", enqueue_after_commit=True)
