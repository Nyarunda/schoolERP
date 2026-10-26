"""M-Pesa Paybill (Daraja C2B) helpers that don't need Frappe."""

import ipaddress
import re
from datetime import datetime

ACCEPT = {"ResultCode": "0", "ResultDesc": "Accepted"}
REJECT_ACCOUNT = {"ResultCode": "C2B00012", "ResultDesc": "Rejected"}  # invalid account number
REJECT_AMOUNT = {"ResultCode": "C2B00013", "ResultDesc": "Rejected"}  # invalid amount
REJECT_OTHER = {"ResultCode": "C2B00016", "ResultDesc": "Rejected"}  # other error

# School Settings > M-Pesa account type. A Till (Buy Goods) has no account number: payments carry no Student ID.
PAYBILL, TILL = "Paybill", "Till (Buy Goods)"


def is_till(account_type: str | None) -> bool:
	return (account_type or "").startswith("Till")


def pay_line(account_type: str | None, number: str | None, account: str | None) -> str:
	"""How a parent pays, in one line for SMS, statements and receipts."""
	if not number:
		return ""
	if is_till(account_type):
		return f"M-Pesa Buy Goods, Till {number}"
	return f"M-Pesa Paybill {number}, Account {account}" if account else f"M-Pesa Paybill {number}"


def stk_parties(account_type: str | None, shortcode: str, till_number: str | None) -> tuple[str, str]:
	"""(TransactionType, PartyB) for an STK push. A Till is paid to the till number, authenticated by its store number."""
	if is_till(account_type):
		return "CustomerBuyGoodsOnline", till_number or shortcode
	return "CustomerPayBillOnline", shortcode

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


def payer_name(payload: dict) -> str:
	return " ".join(p for p in (payload.get("FirstName"), payload.get("MiddleName"), payload.get("LastName")) if p).title()


def normalize_payload(payload: dict) -> dict:
	"""Daraja confirmation/validation JSON -> our field names."""
	return {
		"trans_id": (payload.get("TransID") or "").strip().upper(),
		"trans_time": parse_trans_time(payload.get("TransTime")),
		"amount": float(payload.get("TransAmount") or 0),
		"bill_ref_number": clean_ref(payload.get("BillRefNumber")),
		"msisdn": str(payload.get("MSISDN") or ""),
		"payer_name": payer_name(payload),
		"business_shortcode": str(payload.get("BusinessShortCode") or ""),
		"transaction_type": payload.get("TransactionType") or "",
		"org_account_balance": float(payload.get("OrgAccountBalance") or 0),
	}
