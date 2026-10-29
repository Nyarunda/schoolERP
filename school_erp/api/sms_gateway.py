"""Any HTTP SMS provider, configured on a School SMS Gateway record instead of in code.

The school enters the provider's URL, parameter names, credentials and what a successful reply looks like; this sends
and reads the reply, so a provider that answers HTTP 200 with an error in the body is still recorded as failed.

The URL is typed by a school admin, and every school shares this server: each request resolves the name once, is
refused unless every address is public, and connects to that exact address (TLS still verified against the name).
Nothing re-resolves it, so a gateway cannot be pointed at this server's own network.
"""

import ipaddress
import json
import socket
from urllib.parse import urlencode, urlsplit

import certifi
import frappe
import urllib3
from frappe import _

DOCTYPE = "School SMS Gateway"
PORT = 443
MAX_RESPONSE_BYTES = 64 * 1024


# ----------------------------------------------------------------------------- destination
def _lookup(host):
	return [item[4][0] for item in socket.getaddrinfo(host, PORT, type=socket.SOCK_STREAM)]


def _is_public(address):
	ip = ipaddress.ip_address(address.split("%")[0])
	if ip.version == 6 and ip.ipv4_mapped:
		ip = ip.ipv4_mapped
	return ip.is_global and not ip.is_multicast


def check_url(url):
	"""(parsed, host, address): the one public address requests to this URL go to, or a refusal."""
	parsed = urlsplit((url or "").strip())
	try:
		port = parsed.port
	except ValueError:
		port = -1
	if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or port not in (None, 443):
		frappe.throw(_("The SMS gateway URL must be https:// on the standard port, without a username or password in it"))
	host = parsed.hostname.lower().rstrip(".")
	if host == "localhost" or host.endswith((".localhost", ".local")):
		frappe.throw(_("The SMS gateway URL cannot point at this server"))
	try:
		addresses = _lookup(host)
	except OSError:
		frappe.throw(_("The SMS gateway's address {0} could not be found").format(host))
	if not addresses or not all(_is_public(a) for a in addresses):
		frappe.throw(_("The SMS gateway's address {0} is not a public internet address").format(host))
	return parsed, host, addresses[0]


def _ca_bundle():
	return certifi.where()


def _request(gw, url, method, fields, headers):
	"""One HTTP request to the checked address. Returns (status, body text)."""
	parsed, host, address = check_url(url)
	path = parsed.path or "/"
	query = parsed.query
	body = None
	headers = {"Accept": "application/json, text/plain, */*", **headers, "Host": host}
	if method == "GET":
		query = "&".join(q for q in (query, urlencode(fields)) if q)
	elif gw.body_format == "Form":
		body = urlencode(fields).encode()
		headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
	else:
		body = json.dumps(fields).encode()
		headers.setdefault("Content-Type", "application/json")
	pool = urllib3.HTTPSConnectionPool(address, PORT, cert_reqs="CERT_REQUIRED", ca_certs=_ca_bundle(),
										server_hostname=host, assert_hostname=host, maxsize=1, retries=False,
										timeout=urllib3.Timeout(connect=10, read=max(int(gw.timeout or 20), 5)))
	try:
		response = pool.urlopen(method, path + (f"?{query}" if query else ""), body=body, headers=headers,
								redirect=False, assert_same_host=False, preload_content=False)
		try:
			return response.status, response.read(MAX_RESPONSE_BYTES).decode("utf-8", "replace")
		finally:
			response.release_conn()
	finally:
		pool.close()


# ----------------------------------------------------------------------------- reply
def _field(data, path):
	"""data at a dotted path; list positions are numbers (responses.0.response-code)."""
	for part in (path or "").split("."):
		if isinstance(data, list) and part.lstrip("-").isdigit() and -len(data) <= int(part) < len(data):
			data = data[int(part)]
		elif isinstance(data, dict) and part in data:
			data = data[part]
		else:
			return None
	return data


def succeeded(gw, status, body):
	"""(ok, reason) for one reply, by the gateway's own rule."""
	if not 200 <= status < 300:
		return False, f"HTTP {status}: {body[:200]}"
	if gw.success_field:
		try:
			value = _field(json.loads(body), gw.success_field.strip())
		except ValueError:
			return False, f"The reply is not JSON: {body[:200]}"
		accepted = {v.strip().lower() for v in (gw.success_values or "").split(",") if v.strip()}
		if value is not None and str(value).strip().lower() in accepted:
			return True, ""
		return False, f"{gw.success_field} is {value!r}, not {gw.success_values}: {body[:200]}"
	if gw.success_text:
		if gw.success_text.lower() in body.lower():
			return True, ""
		return False, f"The reply does not contain {gw.success_text!r}: {body[:200]}"
	return True, ""  # no rule set: any 2xx counts (the form warns about this)


# ----------------------------------------------------------------------------- sending
def format_number(number, fmt, country_code="254"):
	"""From the normalised international form (2547XXXXXXXX) to what the gateway expects."""
	if fmt == "+2547XXXXXXXX":
		return "+" + number
	cc = "".join(ch for ch in (country_code or "") if ch.isdigit())
	if fmt == "07XXXXXXXX" and cc and number.startswith(cc):
		return "0" + number[len(cc):]
	return number


def _base(gw):
	fields, headers = {}, {}
	key = gw.get_password("api_key", raise_exception=False)
	if gw.api_key_param and key:
		target = headers if gw.api_key_in == "Header" else fields
		target[gw.api_key_param] = f"{gw.api_key_prefix or ''}{key}"
	if gw.sender_param and gw.sender_id:
		fields[gw.sender_param] = gw.sender_id
	for row in gw.parameters:
		(headers if row.is_header else fields)[row.parameter] = row.value or ""
	return fields, headers, key


def _redact(text, secret):
	return text.replace(secret, "***") if secret else text


def send(gateway, numbers, message, country_code=None):
	"""Send one message to normalised numbers (2547XXXXXXXX). Returns {"sent": [...], "failed": [...], "errors": [...]}.

	`gateway` is a School SMS Gateway (or its name), or any object with the same fields and get_password("api_key"):
	the Control Center sends its own messages to schools through one built from Stemic Settings."""
	gw = frappe.get_doc(DOCTYPE, gateway) if isinstance(gateway, str) else gateway
	if not gw.enabled:
		frappe.throw(_("The SMS gateway {0} is disabled").format(gw.name))
	fields, headers, key = _base(gw)
	cc = country_code or frappe.get_cached_doc("School Settings").country_code or "254"
	batches = [numbers] if gw.recipients_mode == "All numbers in one request" else [[n] for n in numbers]
	sent, failed, errors = [], [], []
	for batch in batches:
		to = (gw.recipient_separator or ",").join(format_number(n, gw.number_format, cc) for n in batch)
		try:
			status, body = _request(gw, gw.url, gw.http_method or "POST",
									{**fields, gw.recipient_param: to, gw.message_param: message}, headers)
			ok, reason = succeeded(gw, status, body)
		except Exception as exc:
			ok, reason = False, getattr(exc, "message", None) or str(exc)
		if ok:
			sent += batch
		else:
			failed += batch
			errors.append(_redact(f"{', '.join(batch)}: {reason}", key))
	if errors:
		frappe.log_error(title=f"SMS gateway {gw.name}: {len(failed)} not sent", message="\n".join(errors)[:5000])
	return {"sent": sent, "failed": failed, "errors": errors}


@frappe.whitelist(methods=["POST"])
def send_test(gateway, number=None):
	"""Send one test SMS through this gateway and show exactly what happened."""
	from school_erp.logic.text import normalize_phone

	frappe.has_permission(DOCTYPE, "write", gateway, throw=True)
	gw = frappe.get_doc(DOCTYPE, gateway)
	settings = frappe.get_cached_doc("School Settings")
	clean = normalize_phone(number or gw.test_number, settings.country_code)
	if not clean:
		frappe.throw(_("Enter a valid test phone number"))
	school = settings.get("school_name") or "School ERP"
	result = send(gw, [clean], _("Test message from {0}: the SMS gateway {1} works.").format(school, gw.name))
	return {"sent": bool(result["sent"]), "number": clean, "error": (result["errors"] or [""])[0]}
