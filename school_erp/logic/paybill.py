"""M-Pesa Paybill (Daraja C2B) helpers that don't need Frappe."""

import ipaddress
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

ACCEPT = {"ResultCode": "0", "ResultDesc": "Accepted"}
REJECT_ACCOUNT = {"ResultCode": "C2B00012", "ResultDesc": "Rejected"}  # invalid account number
REJECT_AMOUNT = {"ResultCode": "C2B00013", "ResultDesc": "Rejected"}  # invalid amount
REJECT_OTHER = {"ResultCode": "C2B00016", "ResultDesc": "Rejected"}  # other error

# Safaricom refuses callback URLs that contain these words
FORBIDDEN_URL_WORDS = ("mpesa", "m-pesa", "safaricom", "exec", "exe", "cmd", "sql", "query")


def account_key(ref: str | None) -> str:
	"""Canonical form for comparing what a parent typed with a Student ID: 'stu 2026-0042 ' -> 'STU20260042'."""
	return re.sub(r"[^A-Z0-9]", "", (ref or "").upper())


def clean_ref(ref: str | None) -> str:
	return " ".join((ref or "").split()).upper()


def parse_trans_time(value: str | None) -> datetime | None:
	"""Daraja TransTime is 'YYYYMMDDHHmmss'."""
	if not value:
		return None
	try:
		return datetime.strptime(str(value).strip()[:14], "%Y%m%d%H%M%S")
	except ValueError:
		return None


def ip_allowed(ip: str | None, allowed: str | list[str] | None) -> bool:
	"""allowed: newline/comma separated IPs or CIDR ranges."""
	if not ip:
		return False
	entries = allowed if isinstance(allowed, list) else re.split(r"[\s,]+", allowed or "")
	try:
		addr = ipaddress.ip_address(ip.strip())
	except ValueError:
		return False
	for e in entries:
		e = e.strip()
		if not e:
			continue
		try:
			if addr in ipaddress.ip_network(e, strict=False):
				return True
		except ValueError:
			continue
	return False


def url_problems(url: str) -> list[str]:
	problems = []
	low = (url or "").lower()
	if not low.startswith(("https://", "http://")):
		problems.append("URL must start with https://")
	for w in FORBIDDEN_URL_WORDS:
		if w in low:
			problems.append(f"URL contains '{w}', which Safaricom rejects")
	if "localhost" in low or "127.0.0.1" in low or ".local" in low:
		problems.append("URL must be reachable from the internet")
	return problems


# Why a confirmation was held for the bursar instead of being posted
ENVELOPE_PROBLEMS = {
	"shortcode": "Business short code does not match the one in School Settings",
	"transaction_id": "No M-Pesa transaction code (TransID)",
	"amount": "Amount is not a positive number with at most 2 decimals",
}


def parse_amount(value) -> float | None:
	"""Daraja TransAmount -> float, or None unless it is a positive, finite amount with at most 2 decimals."""
	try:
		amount = Decimal(str(value).strip())
	except (InvalidOperation, TypeError, ValueError):
		return None
	if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
		return None
	return float(amount)


def envelope_problems(payload: dict, expected_shortcode: str | None, require_transaction_id: bool = True) -> list[str]:
	"""Minimal checks on a raw Daraja C2B payload. Returns ENVELOPE_PROBLEMS keys; empty when it looks right.

	This is not cryptographic origin verification. Reconcile with provider statements.
	"""
	problems = []
	if not expected_shortcode or str(payload.get("BusinessShortCode") or "").strip() != str(expected_shortcode).strip():
		problems.append("shortcode")
	if require_transaction_id and not str(payload.get("TransID") or "").strip():
		problems.append("transaction_id")
	if parse_amount(payload.get("TransAmount")) is None:
		problems.append("amount")
	return problems


def _number(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def payer_name(payload: dict) -> str:
	return " ".join(p for p in (payload.get("FirstName"), payload.get("MiddleName"), payload.get("LastName")) if p).title()


def normalize_payload(payload: dict) -> dict:
	"""Daraja confirmation/validation JSON -> our field names."""
	return {
		"trans_id": (payload.get("TransID") or "").strip().upper(),
		"trans_time": parse_trans_time(payload.get("TransTime")),
		"amount": parse_amount(payload.get("TransAmount")) or 0.0,  # never raises: a bad amount is held for review
		"bill_ref_number": clean_ref(payload.get("BillRefNumber")),
		"msisdn": str(payload.get("MSISDN") or ""),
		"payer_name": payer_name(payload),
		"business_shortcode": str(payload.get("BusinessShortCode") or ""),
		"transaction_type": payload.get("TransactionType") or "",
		"org_account_balance": _number(payload.get("OrgAccountBalance")),
	}
