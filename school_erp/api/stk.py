"""M-Pesa Express (STK Push): a payment prompt on the parent's phone.

Flow
  parent clicks Pay on the portal -> stk_push() asks Safaricom to prompt the phone
  -> parent enters their M-Pesa PIN
  -> Safaricom POSTs the result to /api/method/school_erp.api.stk.callback?token=...
  -> a successful payment is recorded as an M-Pesa Transaction (unique by M-Pesa receipt) and
     posted to the student by the same code as Paybill payments, so it can never be posted twice
     even if the paybill confirmation for the same payment also arrives.
If a callback never arrives, query_stale_requests() asks Safaricom for the result.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now_datetime

from school_erp import licensing
from school_erp.logic.paybill import account_key, stk_parties, valid_stk_metadata
from school_erp.logic.text import normalize_phone

EAT = timezone(timedelta(hours=3))  # Daraja timestamps are East Africa Time
HOSTS = {"Sandbox": "https://sandbox.safaricom.co.ke", "Production": "https://api.safaricom.co.ke"}


def _settings():
	return frappe.get_cached_doc("School Settings")


def _timestamp():
	return datetime.now(EAT).strftime("%Y%m%d%H%M%S")


def _password(shortcode, passkey, timestamp):
	return base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()


def callback_url(settings=None):
	settings = settings or _settings()
	base = (settings.mpesa_callback_base_url or frappe.utils.get_url()).rstrip("/")
	return f"{base}/api/method/school_erp.api.stk.callback?token={settings.mpesa_callback_token}"


def _require_ready(settings):
	licensing.require("portal")
	licensing.require("mpesa")
	if not (settings.mpesa_enabled and settings.mpesa_stk_enabled):
		frappe.throw(_("Online M-Pesa payment is not switched on for this school"))
	if not (settings.mpesa_shortcode and settings.get_password("mpesa_passkey", raise_exception=False)):
		frappe.throw(_("The school has not finished setting up M-Pesa payments (short code / passkey)"))


def initiate(student: str, amount, phone: str, requested_by: str | None = None) -> str:
	"""Send the prompt. Returns the STK Push Request name."""
	import requests

	from school_erp.api.paybill import _token

	settings = frappe.get_doc("School Settings")
	_require_ready(settings)
	amount = cint(round(flt(amount)))
	if amount < 1:
		frappe.throw(_("Enter an amount of at least 1"))
	if amount > 250000:
		frappe.throw(_("M-Pesa allows at most 250,000 per transaction"))
	msisdn = normalize_phone(phone, settings.country_code)
	if not msisdn or not msisdn.startswith("254"):
		frappe.throw(_("Enter a valid Safaricom number, e.g. 0712 345 678"))

	ts = _timestamp()
	transaction_type, party_b = stk_parties(settings.mpesa_account_type, settings.mpesa_shortcode, settings.paybill_number)
	payload = {
		"BusinessShortCode": settings.mpesa_shortcode,
		"Password": _password(settings.mpesa_shortcode, settings.get_password("mpesa_passkey"), ts),
		"Timestamp": ts,
		"TransactionType": transaction_type,
		"Amount": amount,
		"PartyA": msisdn,
		"PartyB": party_b,
		"PhoneNumber": msisdn,
		"CallBackURL": callback_url(settings),
		"AccountReference": account_key(student)[:12],  # Daraja limit: 12 characters (a Till ignores it; the request links the student)
		"TransactionDesc": "School fees",
	}
	req = frappe.get_doc({"doctype": "STK Push Request", "student": student, "amount": amount, "phone": msisdn,
						  "status": "Pending", "requested_by": requested_by or frappe.session.user})
	req.flags.ignore_permissions = True
	req.insert()
	try:
		r = requests.post(f"{HOSTS[settings.mpesa_environment or 'Sandbox']}/mpesa/stkpush/v1/processrequest",
						  json=payload, headers={"Authorization": f"Bearer {_token(settings)}"}, timeout=30)
		body = r.json() if r.text else {}
	except Exception as e:
		req.db_set({"status": "Failed", "result_desc": f"Could not reach M-Pesa: {e}"[:140]})
		frappe.db.commit()
		frappe.throw(_("Could not reach M-Pesa right now. Please try again shortly."))
	if str(body.get("ResponseCode")) != "0":
		req.db_set({"status": "Failed", "result_desc": (body.get("errorMessage") or body.get("ResponseDescription") or str(body))[:140]})
		frappe.db.commit()
		frappe.throw(_("M-Pesa did not accept the request: {0}").format(body.get("errorMessage") or body.get("ResponseDescription") or r.status_code))
	req.db_set({"checkout_request_id": body.get("CheckoutRequestID"), "merchant_request_id": body.get("MerchantRequestID"),
				"result_desc": body.get("CustomerMessage") or "Sent to phone"})
	frappe.db.commit()
	return req.name


def _metadata(cb: dict) -> dict:
	items = (cb.get("CallbackMetadata") or {}).get("Item") or []
	return {i.get("Name"): i.get("Value") for i in items if isinstance(i, dict)}


def apply_result(checkout_request_id: str, result_code, result_desc: str, meta: dict | None = None, source="callback"):
	"""Record the outcome of an STK request (from the callback or a status query)."""
	name = frappe.db.get_value("STK Push Request", {"checkout_request_id": checkout_request_id})
	if not name:
		frappe.log_error(title="STK result for unknown request", message=f"{checkout_request_id}: {result_code} {result_desc}")
		return None
	req = frappe.get_doc("STK Push Request", name, for_update=True)
	if req.status == "Paid":
		return req.name  # already handled (callback + query, or Safaricom retry)
	code = cint(result_code)
	if code != 0:
		status = "Cancelled" if code in (1032, 1037, 1025, 2001) else "Failed"
		req.db_set({"status": status, "result_desc": (result_desc or "")[:140]})
		frappe.db.commit()
		return req.name

	meta = meta or {}
	if not valid_stk_metadata(meta, req.amount, req.phone):
		req.db_set({"result_desc": "STK success lacks matching provider receipt, amount or phone; requires investigation"})
		frappe.db.commit()
		frappe.log_error(title="STK result needs reconciliation", message=f"Checkout {checkout_request_id}: incomplete or mismatched success metadata")
		return req.name
	receipt = str(meta.get("MpesaReceiptNumber") or "").upper()
	if not receipt:
		# a status query says "paid" but carries no receipt: wait for the callback / C2B confirmation
		req.db_set({"result_desc": "Paid - waiting for the M-Pesa receipt"})
		frappe.db.commit()
		return req.name
	from school_erp.api.paybill import record_confirmation

	raw = {
		"TransactionType": "STK Push", "TransID": receipt,
		"TransTime": str(meta.get("TransactionDate") or now_datetime().strftime("%Y%m%d%H%M%S")),
		"TransAmount": str(meta["Amount"]), "BusinessShortCode": _settings().mpesa_shortcode,
		"BillRefNumber": req.student, "MSISDN": str(meta.get("PhoneNumber") or req.phone), "FirstName": "Parent Portal",
	}
	tx = record_confirmation(raw, source="STK Push")
	frappe.db.set_value("M-Pesa Transaction", tx, "student", req.student)
	req.db_set({"status": "Paid", "result_desc": (result_desc or "Paid")[:140], "mpesa_receipt": receipt, "mpesa_transaction": tx})
	frappe.db.commit()
	return req.name


@frappe.whitelist(allow_guest=True, methods=["POST"])
def callback():
	"""Safaricom posts the STK result here."""
	from school_erp.api.paybill import _authorised, _json_response, _payload
	from school_erp.logic.paybill import ACCEPT, REJECT_OTHER

	settings = _settings()
	reason = _authorised(settings)
	raw = _payload()
	if reason:
		frappe.log_error(title="STK callback refused", message=f"{reason}\n{json.dumps(raw)[:2000]}")
		return _json_response(REJECT_OTHER, status=403)
	try:
		cb = (raw.get("Body") or {}).get("stkCallback") or {}
		previous = frappe.session.user
		frappe.set_user("Administrator")
		try:
			apply_result(cb.get("CheckoutRequestID"), cb.get("ResultCode"), cb.get("ResultDesc"), _metadata(cb))
		finally:
			frappe.set_user(previous)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="STK callback could not be processed", message=json.dumps(raw)[:4000])
		return _json_response(REJECT_OTHER, status=503)
	return _json_response(ACCEPT)


def query(req_name: str):
	"""Ask Safaricom for the result of a request whose callback hasn't arrived."""
	import requests

	from school_erp.api.paybill import _token

	settings = frappe.get_doc("School Settings")
	req = frappe.get_doc("STK Push Request", req_name)
	if req.status != "Pending" or not req.checkout_request_id:
		return req.status
	ts = _timestamp()
	try:
		r = requests.post(f"{HOSTS[settings.mpesa_environment or 'Sandbox']}/mpesa/stkpushquery/v1/query", timeout=30,
						  json={"BusinessShortCode": settings.mpesa_shortcode, "Timestamp": ts, "CheckoutRequestID": req.checkout_request_id,
								"Password": _password(settings.mpesa_shortcode, settings.get_password("mpesa_passkey"), ts)},
						  headers={"Authorization": f"Bearer {_token(settings)}"})
		body = r.json() if r.text else {}
	except Exception:
		return req.status
	req.db_set("last_queried", now_datetime())
	if "ResultCode" in body:  # final answer; still-processing returns an error code instead
		apply_result(req.checkout_request_id, body.get("ResultCode"), body.get("ResultDesc"), source="query")
	frappe.db.commit()
	return frappe.db.get_value("STK Push Request", req_name, "status")


def query_stale_requests():
	"""Every 5 minutes: check pending requests older than 2 minutes; give up after 30 minutes."""
	if not licensing.is_enabled("portal"):
		return
	now = now_datetime()
	for r in frappe.get_all("STK Push Request", filters={"status": "Pending", "creation": ("<", add_to_date(now, minutes=-2))},
							fields=["name", "creation", "checkout_request_id"], limit=50):
		if not r.checkout_request_id or r.creation < add_to_date(now, minutes=-30):
			frappe.db.set_value("STK Push Request", r.name, {"status": "Failed", "result_desc": "No response from M-Pesa"})
			continue
		query(r.name)
	frappe.db.commit()


def status(req_name: str) -> dict:
	row = frappe.db.get_value("STK Push Request", req_name, ["status", "result_desc", "mpesa_receipt", "creation", "student"], as_dict=True)
	if row and row.status == "Pending" and row.creation < add_to_date(now_datetime(), seconds=-25):
		row.status = query(req_name) or row.status
	return row
