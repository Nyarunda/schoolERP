"""M-Pesa Paybill auto-posting (Safaricom Daraja C2B).

Flow
  parent pays Paybill, Account No = Student ID
  -> Safaricom POSTs to  /api/method/school_erp.api.paybill.confirm?token=...
  -> we store an "M-Pesa Transaction" (unique by M-Pesa code, so retries never double-post)
  -> a background job matches the Student and submits a Fee Payment
     (Payment Entry posted, balance reduced, parent gets the receipt SMS)
  -> payments with an unknown account number wait as "Unmatched" for the bursar to assign.
  -> a Till (Buy Goods) payment has no account number: it is matched by the payer's phone when exactly one
     active student has a guardian with that number (Safaricom often masks it), otherwise it waits as "Unmatched".

The endpoint path deliberately avoids the word "mpesa": Safaricom rejects such callback URLs.
"""

import json
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime
from werkzeug.wrappers import Response

from school_erp import licensing
from school_erp.logic import paybill as pb
from school_erp.logic.text import normalize_phone

MAX_ATTEMPTS = 5
DARAJA_HOST = {"Sandbox": "https://sandbox.safaricom.co.ke", "Production": "https://api.safaricom.co.ke"}


# ----------------------------------------------------------------------------- helpers
def our_shortcodes(settings) -> list[str]:
	"""Codes Safaricom may put in BusinessShortCode for this school: the Paybill, or a Till's store and till numbers."""
	codes = [settings.mpesa_shortcode]
	if pb.is_till(settings.mpesa_account_type):
		codes.append(settings.paybill_number)
	return [c for c in codes if c]


def _settings():
	return frappe.get_cached_doc("School Settings")


def _json_response(data: dict, status: int = 200) -> Response:
	return Response(json.dumps(data), status=status, mimetype="application/json")


def _payload() -> dict:
	try:
		data = frappe.request.get_json(silent=True, force=True)
	except Exception:
		data = None
	if not data:
		data = {k: v for k, v in frappe.form_dict.items() if k not in ("cmd", "token")}
	return data or {}


def _authorised(settings) -> str | None:
	"""Return a reason string if the callback must be refused."""
	if not settings.mpesa_enabled:
		return "auto-posting disabled"
	# Safaricom posts JSON, and Frappe builds form_dict from a JSON body alone, so the ?token= has to be read off the URL
	token = frappe.form_dict.get("token") or (frappe.request.args.get("token") if getattr(frappe.local, "request", None) else None)
	if not settings.mpesa_callback_token or not secrets.compare_digest(str(token or ""), str(settings.mpesa_callback_token)):
		return "bad token"
	if settings.mpesa_check_ip and not pb.ip_allowed(frappe.local.request_ip, settings.mpesa_allowed_ips):
		return f"IP {frappe.local.request_ip} not allowed"
	return None


def find_student(bill_ref: str) -> str | None:
	"""Match what the parent typed to a Student ID (or admission number). Tolerates case, spaces and hyphens."""
	ref = pb.clean_ref(bill_ref)
	if not ref:
		return None
	name = frappe.db.get_value("Student", {"name": ref}) or frappe.db.get_value("Student", {"admission_number": ref})
	if name:
		return name
	key = pb.account_key(ref)
	if len(key) < 3:
		return None
	rows = frappe.db.sql(
		"""select name from `tabStudent`
		where upper(regexp_replace(name, '[^A-Za-z0-9]', '')) = %(k)s
		   or upper(regexp_replace(ifnull(admission_number, ''), '[^A-Za-z0-9]', '')) = %(k)s
		limit 2""",
		{"k": key},
	)
	return rows[0][0] if len(rows) == 1 else None  # ambiguous -> let the bursar decide


def find_student_by_phone(msisdn: str | None) -> str | None:
	"""The one active student whose guardian has this phone number, for payments without an account number (Tills).
	Safaricom masks the number in most C2B callbacks ("2547 ***** 126"); those, and shared numbers, return None."""
	if not msisdn or "*" in msisdn:
		return None
	cc = _settings().country_code
	phone = normalize_phone(msisdn, cc)
	if not phone:
		return None
	rows = frappe.db.sql(
		"""select distinct g.parent, g.mobile_no from `tabStudent Guardian` g join `tabStudent` s on s.name = g.parent
		where g.parenttype = 'Student' and s.status = 'Active' and ifnull(g.mobile_no, '') != ''""",
		as_dict=True,
	)
	students = {r.parent for r in rows if normalize_phone(r.mobile_no, cc) == phone}
	return students.pop() if len(students) == 1 else None  # a parent of siblings: let the bursar choose


# ----------------------------------------------------------------------------- Safaricom callbacks
@frappe.whitelist(allow_guest=True, methods=["POST"])
def validate():
	"""Called before the payment completes, only if Safaricom activated External Validation for the paybill."""
	settings = _settings()
	reason = _authorised(settings)
	if reason:
		frappe.log_error(title="Paybill validation refused", message=reason)
		return _json_response(pb.REJECT_OTHER)
	data = pb.normalize_payload(_payload())
	if not pb.valid_confirmation(_payload(), our_shortcodes(settings), require_transaction_id=False):
		return _json_response(pb.REJECT_AMOUNT)
	if settings.mpesa_validate_account and not pb.is_till(settings.mpesa_account_type) and not find_student(data["bill_ref_number"]):
		return _json_response(pb.REJECT_ACCOUNT)
	return _json_response(pb.ACCEPT)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def confirm():
	"""Called after the parent's money has reached the paybill. Always answer quickly."""
	settings = _settings()
	reason = _authorised(settings)
	raw = _payload()
	if reason:
		frappe.log_error(title="Paybill confirmation refused", message=f"{reason}\n{json.dumps(raw)[:2000]}")
		return _json_response(pb.REJECT_OTHER, status=403)
	problems = pb.confirmation_problems(raw, our_shortcodes(settings))
	if problems:
		# The request carried our secret token, so this is most likely a real payment with odd details (a changed
		# short code, say). Refuse to post it, but keep it where the bursar will see it rather than only in a log.
		frappe.log_error(title="Invalid Paybill confirmation", message=f"{'; '.join(problems)}\n{json.dumps(raw)[:2000]}")
		if not hold_for_review(raw, problems):
			return _json_response(pb.REJECT_OTHER, status=503)
		return _json_response(pb.ACCEPT)
	try:
		record_confirmation(raw, source="Safaricom")
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Paybill confirmation could not be stored", message=json.dumps(raw)[:4000])
		return _json_response(pb.REJECT_OTHER, status=503)
	return _json_response(pb.ACCEPT)


def hold_for_review(raw: dict, problems: list[str]) -> str | None:
	"""Keep a confirmation that failed its checks as "Needs Review": never posted automatically, visible to the bursar.
	Without a transaction code there is nothing to key it on, so it stays in the Error Log only."""
	trans_id = str((raw or {}).get("TransID") or "").strip()[:140] if isinstance(raw, dict) else ""
	if not trans_id or frappe.db.exists("M-Pesa Transaction", trans_id):
		return None
	try:
		data = pb.normalize_payload(raw)
	except (TypeError, ValueError):
		data = {"trans_id": trans_id}
	if not pb.valid_money(raw.get("TransAmount")):
		data["amount"] = 0
	try:
		doc = frappe.get_doc({
			"doctype": "M-Pesa Transaction", **data, "trans_id": trans_id,
			"trans_time": data.get("trans_time") or now_datetime(), "status": "Needs Review", "source": "Safaricom",
			"error": "Held for review: " + "; ".join(problems), "raw_payload": json.dumps(raw, indent=1, default=str),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		frappe.db.commit()
		return doc.name
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Paybill confirmation could not be held for review", message=json.dumps(raw)[:4000])
		return None


def record_confirmation(raw: dict, source: str = "Safaricom") -> str:
	"""Store a validated transaction (idempotent) and queue posting."""
	if source == "Safaricom" and not pb.valid_confirmation(raw, our_shortcodes(_settings())):
		frappe.throw(_("Invalid Paybill confirmation envelope"))
	data = pb.normalize_payload(raw)
	if not data["trans_id"]:
		frappe.throw(_("Missing TransID"))
	if frappe.db.exists("M-Pesa Transaction", data["trans_id"]):
		return data["trans_id"]  # Safaricom retry: already have it

	doc = frappe.get_doc(
		{
			"doctype": "M-Pesa Transaction",
			**data,
			"trans_time": data["trans_time"] or now_datetime(),
			"status": "Received",
			"source": source,
			"raw_payload": json.dumps(raw, indent=1, default=str),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	# Commit the inbox row before ACK. An enqueue outage must not lose the payment:
	# retry_pending() scans durable Received rows.
	frappe.db.commit()
	try:
		frappe.enqueue(
			"school_erp.api.paybill.post_transaction",
			queue="short", name=doc.name, now=bool(frappe.flags.in_test),
			job_id=f"school-paybill-{doc.name}",
		)
	except Exception:
		frappe.log_error(title=f"Paybill worker queue unavailable for {doc.name}")

	return doc.name


# ----------------------------------------------------------------------------- posting
def post_transaction(name: str, student: str | None = None) -> str:
	"""Turn a stored M-Pesa transaction into a submitted Fee Payment. Safe to call repeatedly."""
	previous_user = frappe.session.user
	frappe.set_user("Administrator")  # callbacks arrive as Guest
	try:
		return _post(name, student)
	finally:
		frappe.set_user(previous_user)


def _post(name, student=None):
	tx = frappe.get_doc("M-Pesa Transaction", name, for_update=True)
	if tx.status in ("Posted", "Ignored", "Needs Review"):
		return tx.status

	if not licensing.is_enabled("mpesa"):
		tx.db_set({"status": "Failed", "error": "M-Pesa auto-posting is not part of this school's subscription"})
		return tx.status

	student = student or tx.student or find_student(tx.bill_ref_number) or find_student_by_phone(tx.msisdn)
	if not student:
		if tx.bill_ref_number:
			why = f"No student with ID '{tx.bill_ref_number}'"
		elif "*" in (tx.msisdn or ""):
			why = "No account number and Safaricom hid the payer's phone: assign the student"
		else:
			why = f"No account number and no single student whose guardian has phone {tx.msisdn}: assign the student"
		tx.db_set({"status": "Unmatched", "error": why})
		frappe.publish_realtime("paybill_unmatched", {"name": tx.name, "amount": tx.amount}, after_commit=True)
		return tx.status

	existing = frappe.db.get_value("Fee Payment", {"reference_no": tx.trans_id, "docstatus": 1})
	if existing:  # already receipted (e.g. bursar entered it by hand)
		tx.db_set({"status": "Posted", "student": student, "fee_payment": existing, "error": None})
		return tx.status

	settings = _settings()
	try:
		fp = frappe.get_doc(
			{
				"doctype": "Fee Payment",
				"student": student,
				"posting_date": getdate(tx.trans_time or now_datetime()),
				"mode_of_payment": settings.mpesa_mode_of_payment or settings.default_mode_of_payment,
				"amount": tx.amount,
				"reference_no": tx.trans_id,
				"payer_name": tx.payer_name,
				"payer_phone": tx.msisdn,
				"allocation_method": "Oldest balance first",
				"remarks": f"Auto-posted from Paybill {tx.business_shortcode}, account '{tx.bill_ref_number}'",
			}
		)
		fp.flags.ignore_permissions = True
		fp.insert()
		fp.submit()
		tx.db_set({"status": "Posted", "student": student, "fee_payment": fp.name, "error": None,
				   "attempts": (tx.attempts or 0) + 1})
		frappe.db.commit()
		return "Posted"
	except Exception as e:
		frappe.db.rollback()
		frappe.db.set_value(
			"M-Pesa Transaction", name,
			{"status": "Failed", "student": student, "error": str(e)[:500], "attempts": (tx.attempts or 0) + 1},
		)
		frappe.db.commit()
		frappe.log_error(title=f"Paybill posting failed for {name}")
		return "Failed"


@frappe.whitelist()
def assign_and_post(name, student=None):
	"""Bursar button: post an Unmatched/Failed/Needs Review payment (optionally to a chosen student)."""
	frappe.has_permission("M-Pesa Transaction", "write", name, throw=True)
	frappe.has_permission("Fee Payment", "submit", throw=True)
	if frappe.db.get_value("M-Pesa Transaction", name, "status") == "Needs Review":
		frappe.throw(_("Reconcile rejected callback evidence with Safaricom before posting"), frappe.PermissionError)
	if student:
		frappe.db.set_value("M-Pesa Transaction", name, "student", student)
	status = post_transaction(name, student)
	return {"status": status, "error": frappe.db.get_value("M-Pesa Transaction", name, "error")}


def retry_pending():
	"""Hourly: retry Failed posts and anything stuck in Received (e.g. the worker was down)."""
	cutoff = add_to_date(now_datetime(), minutes=-10)
	names = frappe.get_all(
		"M-Pesa Transaction",
		filters={"status": ("in", ["Received", "Failed"]), "attempts": ("<", MAX_ATTEMPTS), "creation": ("<", cutoff)},
		pluck="name",
		limit=200,
	)
	for n in names:
		post_transaction(n)


# ----------------------------------------------------------------------------- Daraja API (outbound)
def callback_urls(settings=None) -> dict:
	settings = settings or _settings()
	base = (settings.mpesa_callback_base_url or frappe.utils.get_url()).rstrip("/")
	q = f"?token={settings.mpesa_callback_token}"
	return {
		"confirmation": f"{base}/api/method/school_erp.api.paybill.confirm{q}",
		"validation": f"{base}/api/method/school_erp.api.paybill.validate{q}",
	}


def _token(settings) -> str:
	import requests

	secret = settings.get_password("mpesa_consumer_secret", raise_exception=False)
	if not (settings.mpesa_consumer_key and secret):
		frappe.throw(_("Enter the Daraja Consumer Key and Secret in School Settings > M-Pesa"))
	r = requests.get(
		f"{DARAJA_HOST[settings.mpesa_environment or 'Sandbox']}/oauth/v1/generate?grant_type=client_credentials",
		auth=(settings.mpesa_consumer_key, secret),
		timeout=30,
	)
	if r.status_code != 200:
		if "html" in r.headers.get("content-type", "").lower() or r.text.lstrip().startswith("<"):
			# Safaricom's firewall answers with an HTML page (often after many requests in a short time)
			frappe.throw(_("Safaricom's gateway turned the request away ({0}). Please try again in a minute.").format(r.status_code))
		frappe.throw(_("Safaricom rejected the Consumer Key/Secret ({0}): {1}").format(r.status_code, r.text[:300]))
	return r.json()["access_token"]


@frappe.whitelist()
def register_urls():
	"""Tell Safaricom where to send Paybill notifications. Run once per paybill (and after changing the site URL)."""
	import requests

	frappe.only_for(["System Manager", "School Admin"])
	licensing.require("mpesa")
	settings = frappe.get_doc("School Settings")
	if not settings.mpesa_shortcode:
		frappe.throw(_("Enter the Paybill Short Code"))
	urls = callback_urls(settings)
	problems = pb.url_problems(urls["confirmation"].split("?")[0])
	if settings.mpesa_environment == "Production" and not urls["confirmation"].startswith("https://"):
		problems.append("Production requires https")
	if problems:
		frappe.throw("<br>".join(problems), title=_("Callback URL not acceptable to Safaricom"))

	r = requests.post(
		f"{DARAJA_HOST[settings.mpesa_environment or 'Sandbox']}/mpesa/c2b/v2/registerurl",
		json={
			"ShortCode": settings.mpesa_shortcode,
			"ResponseType": settings.mpesa_response_type or "Completed",
			"ConfirmationURL": urls["confirmation"],
			"ValidationURL": urls["validation"],
		},
		headers={"Authorization": f"Bearer {_token(settings)}"},
		timeout=30,
	)
	body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:500]}
	if r.status_code != 200 or str(body.get("ResponseCode", "0")) not in ("0", "00000000"):
		frappe.throw(_("Safaricom did not accept the URLs: {0}").format(body), title=_("Registration failed"))
	frappe.db.set_single_value("School Settings", "mpesa_registered_on", now_datetime())
	return {"response": body, "urls": urls}


@frappe.whitelist()
def simulate(amount, bill_ref_number=None, msisdn="254708374149"):
	"""Sandbox only: ask Safaricom to send a test payment to the registered URLs."""
	import requests

	frappe.only_for(["System Manager", "School Admin"])
	settings = frappe.get_doc("School Settings")
	if settings.mpesa_environment != "Sandbox":
		frappe.throw(_("Simulation only works in the Sandbox environment"))
	body = {
		"ShortCode": settings.mpesa_shortcode,
		"CommandID": "CustomerBuyGoodsOnline" if pb.is_till(settings.mpesa_account_type) else "CustomerPayBillOnline",
		"Amount": int(float(amount)),
		"Msisdn": msisdn,
	}
	if not pb.is_till(settings.mpesa_account_type):
		body["BillRefNumber"] = bill_ref_number  # a till has no account number; Safaricom refuses an empty one
	r = requests.post(
		f"{DARAJA_HOST['Sandbox']}/mpesa/c2b/v2/simulate",
		json=body,
		headers={"Authorization": f"Bearer {_token(settings)}"},
		timeout=30,
	)
	return r.json() if r.text else {"status": r.status_code}


@frappe.whitelist()
def local_test_payment(amount, bill_ref_number=None, payer="Test Parent", msisdn=None):
	"""Feed a fake confirmation through the real posting code, without Safaricom or internet.
	Only allowed in developer mode or Sandbox, because it creates real accounting entries."""
	frappe.only_for(["System Manager", "School Admin"])
	settings = _settings()
	if not (frappe.conf.developer_mode or settings.mpesa_environment == "Sandbox"):
		frappe.throw(_("Test payments are only allowed in Sandbox or developer mode"))
	first, _sp, last = payer.partition(" ")
	code = "TST" + frappe.generate_hash(length=7).upper()
	name = record_confirmation(
		{
			"TransactionType": "Buy Goods" if pb.is_till(settings.mpesa_account_type) else "Pay Bill",
			"TransID": code,
			"TransTime": now_datetime().strftime("%Y%m%d%H%M%S"),
			"TransAmount": str(amount),
			"BusinessShortCode": settings.mpesa_shortcode or "600000",
			"BillRefNumber": bill_ref_number or "",
			"MSISDN": msisdn or "2547 ***** 126",
			"FirstName": first,
			"LastName": last,
		},
		source="Test",
	)
	if not frappe.flags.in_test:
		post_transaction(name)  # run now so the bursar sees the result immediately
	return frappe.db.get_value("M-Pesa Transaction", name, ["name", "status", "student", "fee_payment", "error"], as_dict=True)
