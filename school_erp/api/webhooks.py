"""Tenant-local signed outbound webhooks. Explicit event allowlist, no automatic DocType subscription.

Destinations are untrusted: a school admin types the URL, and its DNS is controlled by whoever owns the name. Each
delivery resolves the name once, refuses it unless every address is public, and then connects to that exact address
(TLS still verified against the name). The HTTP client never resolves the name again, so a DNS answer that changes
after the check (DNS rebinding) cannot point a delivery at this server's network.
"""
import hashlib
import hmac
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import certifi
import frappe
import urllib3
from frappe.utils import add_to_date, now_datetime

ENDPOINT = "School Webhook Endpoint"
DELIVERY = "School Webhook Delivery"
ALLOWED_EVENTS = {"student.created", "fee_payment.posted", "invoice.submitted"}
PORT = 443
MAX_RESPONSE_BYTES = 64 * 1024


def _lookup(host):
	"""Every address the name resolves to (one DNS answer)."""
	return [item[4][0] for item in socket.getaddrinfo(host, PORT, type=socket.SOCK_STREAM)]


def _is_public(address):
	ip = ipaddress.ip_address(address.split("%")[0])
	if ip.version == 6 and ip.ipv4_mapped:
		ip = ip.ipv4_mapped
	return ip.is_global and not ip.is_multicast


def _parse(url):
	parsed = urlsplit(url or "")
	try:
		port = parsed.port
	except ValueError:
		port = -1
	if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or port not in (None, 443):
		frappe.throw("Webhook requires an HTTPS URL on port 443 without credentials")
	host = parsed.hostname.lower().rstrip(".")
	if host == "localhost" or host.endswith((".localhost", ".local")):
		frappe.throw("Local webhook destinations are prohibited")
	return parsed, host


def resolve_target(url):
	"""(host, address): the one public address this delivery will connect to, or a refusal."""
	_, host = _parse(url)
	try:
		addresses = _lookup(host)
	except OSError:
		frappe.throw("Webhook hostname could not be resolved")
	if not addresses:
		frappe.throw("Webhook hostname could not be resolved")
	# all of them, not just the first: a name with one public and one private address is refused
	if not all(_is_public(a) for a in addresses):
		frappe.throw("Webhook target resolves to a non-public address")
	return host, addresses[0]


def validate_target(url):
	resolve_target(url)
	return url


def sign(body, secret):
	return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _post(url, body, headers):
	"""POST to the address resolved and checked here, never re-resolving the name. Returns the status code."""
	parsed, _ = _parse(url)
	host, address = resolve_target(url)
	path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
	# no proxies, no redirects, no retries: one request to the checked address
	pool = urllib3.HTTPSConnectionPool(address, PORT, cert_reqs="CERT_REQUIRED", ca_certs=_ca_bundle(),
										server_hostname=host, assert_hostname=host, maxsize=1, retries=False,
										timeout=urllib3.Timeout(connect=5, read=10))
	try:
		response = pool.urlopen("POST", path, body=body.encode(), headers={**headers, "Host": host}, redirect=False,
								assert_same_host=False, preload_content=False)
		try:
			response.read(MAX_RESPONSE_BYTES)
			return response.status
		finally:
			response.release_conn()
	finally:
		pool.close()


def _ca_bundle():
	return certifi.where()


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
			frappe.get_doc({"doctype": DELIVERY, "delivery_key": key, "endpoint": ep.name,
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
		frappe.db.set_value(DELIVERY, name, {"status": "Failed", "next_attempt_at": None})
		return
	frappe.db.set_value(DELIVERY, name, {"status": "Sending", "attempts": attempt})
	frappe.db.commit()
	if not endpoint.enabled:
		frappe.db.set_value(DELIVERY, name, {"status": "Failed", "error": "Endpoint disabled"})
		return
	try:
		body = delivery.payload
		status = _post(endpoint.endpoint_url, body, {"Content-Type": "application/json",
													 "X-Stemic-Event": delivery.event_type,
													 "X-Stemic-Delivery": delivery.name,
													 "X-Stemic-Signature-SHA256": sign(body, endpoint.get_password("secret"))})
		if 200 <= status < 300:
			frappe.db.set_value(DELIVERY, name, {"status": "Accepted", "response_code": status, "error": None,
												 "next_attempt_at": None})
		else:
			raise RuntimeError(f"HTTP {status}")
	except Exception as exc:
		again = attempt < cap
		frappe.db.set_value(DELIVERY, name, {"status": "Retrying" if again else "Failed",
											 "error": str(exc)[:300],
											 "next_attempt_at": add_to_date(now_datetime(), minutes=2**attempt) if again else None})


def retry_due():
	names = frappe.get_all(DELIVERY, filters={"status": "Retrying", "next_attempt_at": ("<=", now_datetime())},
						   pluck="name", limit=100)
	for name in names:
		frappe.enqueue("school_erp.api.webhooks.deliver", name=name, queue="short", enqueue_after_commit=True)


# Producers (doc_events). Events are thin: identifiers only, no names, phone numbers or amounts. A receiver that needs
# more reads it through the API with its own credentials, so what leaves the school is only what that user may see.
# The delivery rows are written in the document's own transaction (rolled back with it) and sent after commit.

def _emit(event_type, doc, data):
	try:
		if not frappe.db.exists(ENDPOINT, {"enabled": 1}):
			return
		event_id = f"{doc.doctype}:{doc.name}:{event_type}"
		publish(event_id, event_type, {"id": event_id, "type": event_type, "site": frappe.local.site,
									   "occurred_at": str(now_datetime()), "data": data})
	except Exception:
		# a webhook problem never stops the school's own work
		frappe.log_error(title=f"Webhook event {event_type} not recorded", reference_doctype=doc.doctype,
						 reference_name=doc.name)


def on_student_insert(doc, method=None):
	_emit("student.created", doc, {"student": doc.name, "school_class": doc.school_class})


def on_fee_payment_submit(doc, method=None):
	_emit("fee_payment.posted", doc, {"fee_payment": doc.name, "student": doc.student, "posting_date": str(doc.posting_date)})


def on_sales_invoice_submit(doc, method=None):
	if not doc.get("student") or doc.get("is_return"):
		return
	_emit("invoice.submitted", doc, {"invoice": doc.name, "student": doc.student, "school_term": doc.get("school_term"),
									 "posting_date": str(doc.posting_date)})
