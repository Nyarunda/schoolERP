"""License keys: a signed JSON payload that lists the modules a school has paid for.

Key format:  base64url(payload_json) + "." + base64url(ed25519_signature)

The vendor signs with a private key (tools/license_tool.py); the app only holds the public key,
so a school cannot grant itself extra modules by editing the key.
"""

import base64
import json
from datetime import date, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

CORE = "core"

# Module code -> label. "core" (students, classes, streams, teachers, years, terms) is always on.
MODULES = {
	"fees": "Fees, Payments & Statements",
	"timetable": "Timetable",
	"transport": "Transport",
	"lunch": "Lunch",
	"activities": "Games & Activities",
	"messaging": "SMS & Email to Parents",
	"mpesa": "M-Pesa Paybill Auto-posting",
	"staff": "Staff, Leave & Duty Reports",
	"welfare": "Discipline & Complaints",
	"expenses": "Expenses & Approvals",
	"transport_ops": "Driver Daily Logs & Vehicles",
	"exams": "Exams & Report Cards",
	"portal": "Parent Portal & Online Fee Payment",
	"admissions": "Online Admissions",
}

# Which module each DocType belongs to
DOCTYPE_MODULE = {
	"School Fee Structure": "fees",
	"Fee Type": "fees",
	"Fee Billing Run": "fees",
	"Fee Payment": "fees",
	"Transport Route": "transport",
	"School Activity": "activities",
	"Timetable": "timetable",
	"Subject": "timetable",
	"Period": "timetable",
	"School Message": "messaging",
	"School SMS Gateway": "messaging",
	"Staff Member": "staff",
	"Leave Type": "staff",
	"Leave Application": "staff",
	"Duty Roster": "staff",
	"Duty Report": "staff",
	"Discipline Incident": "welfare",
	"Complaint": "welfare",
	"Expense Category": "expenses",
	"School Expense": "expenses",
	"Withholding Tax Type": "expenses",
	"School Vehicle": "transport_ops",
	"Driver Daily Log": "transport_ops",
	"Grading Scale": "exams",
	"Exam": "exams",
	"Exam Mark Sheet": "exams",
	"Report Card": "exams",
	"CBC Settings": "exams",
	"CBC Strand": "exams",
	"Competency Assessment": "exams",
	"CBC Progress Report": "exams",
	"STK Push Request": "portal",
	"Admission Application": "admissions",
	"Admission Settings": "admissions",
}

# DocTypes another module's forms link to: still readable when that module is licensed, so its forms keep working
READABLE_WITH = {
	"Subject": {"exams"},  # exam mark sheets and report cards list subjects
	"Fee Type": {"transport", "activities", "lunch"},
	"Staff Member": {"welfare", "transport_ops", "transport"},
	"School Vehicle": {"transport", "staff"},
	"Transport Route": {"transport_ops"},
}


def hidden_doctypes(modules) -> set[str]:
	"""DocTypes a school with these modules must not see at all: not in menus, search, lists, reports or reads."""
	modules = set(modules)
	return {dt for dt, module in DOCTYPE_MODULE.items()
			if module not in modules and not (READABLE_WITH.get(dt, set()) & modules)}


# Fee categories that need an extra module on top of "fees"
CATEGORY_MODULE = {"Transport": "transport", "Lunch": "lunch", "Activity": "activities"}

# DocTypes that stay writable after a license expires, so a school can always receipt money
ALWAYS_WRITABLE = {"Fee Payment"}

GRACE_DAYS = 14


class LicenseError(Exception):
	pass


def _b64e(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(text: str) -> bytes:
	text = text.strip()
	return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def generate_keypair():
	"""Return (private_key_b64, public_key_b64), raw 32-byte keys."""
	from cryptography.hazmat.primitives import serialization

	priv = Ed25519PrivateKey.generate()
	priv_raw = priv.private_bytes(
		serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
	)
	pub_raw = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
	return _b64e(priv_raw), _b64e(pub_raw)


def issue(payload: dict, private_key_b64: str) -> str:
	unknown = set(payload.get("modules", [])) - set(MODULES)
	if unknown:
		raise LicenseError(f"Unknown modules: {', '.join(sorted(unknown))}")
	body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
	priv = Ed25519PrivateKey.from_private_bytes(_b64d(private_key_b64))
	return f"{_b64e(body)}.{_b64e(priv.sign(body))}"


def verify(key: str, public_key_b64: str) -> dict:
	if not key or "." not in key:
		raise LicenseError("License key is missing or malformed")
	if not public_key_b64 or public_key_b64.startswith("REPLACE"):
		raise LicenseError("Vendor public key has not been configured in school_erp/licensing/public_key.py")
	body_b64, sig_b64 = "".join(key.split()).split(".", 1)
	try:
		body, sig = _b64d(body_b64), _b64d(sig_b64)
		Ed25519PublicKey.from_public_bytes(_b64d(public_key_b64)).verify(sig, body)
	except (InvalidSignature, ValueError) as e:
		raise LicenseError("License key signature is not valid") from e
	return json.loads(body)


def _to_date(value):
	if not value:
		return None
	if isinstance(value, date):
		return value
	return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def evaluate(key: str, public_key_b64: str, today: date, site: str | None = None) -> dict:
	"""Turn a key into the effective license state used everywhere in the app."""
	state = {
		"status": "unlicensed",
		"modules": [CORE],
		"writable": True,
		"licensed_to": None,
		"expires": None,
		"days_left": None,
		"max_students": 0,
		"issued": None,
		"site": None,
		"message": "No license key. Only Students, Classes and Streams are available.",
	}
	if not key:
		return state
	try:
		payload = verify(key, public_key_b64)
	except LicenseError as e:
		state.update(status="invalid", message=str(e))
		return state

	if payload.get("site") and site and payload["site"].lower() != site.lower():
		state.update(status="invalid", message=f"This key is for {payload['site']}, not {site}")
		return state

	expires = _to_date(payload.get("expires"))
	modules = [CORE] + [m for m in payload.get("modules", []) if m in MODULES]
	state.update(
		modules=modules,
		licensed_to=payload.get("school"),
		expires=expires.isoformat() if expires else None,
		max_students=int(payload.get("max_students") or 0),
		issued=payload.get("issued"),
		site=payload.get("site"),
	)

	if not expires:
		state.update(status="valid", message="License active (no expiry)")
		return state

	days_left = (expires - today).days
	state["days_left"] = days_left
	if days_left >= 0:
		state.update(status="valid", message=f"License active until {expires:%d %b %Y}")
		if days_left <= 30:
			state["message"] += f" ({days_left} days left)"
	elif days_left >= -GRACE_DAYS:
		state.update(
			status="grace",
			message=f"License expired on {expires:%d %b %Y}. Renew within {GRACE_DAYS + days_left} days to avoid interruption.",
		)
	else:
		state.update(
			status="expired",
			writable=False,
			message=f"License expired on {expires:%d %b %Y}. Records are read-only; payments can still be received.",
		)
	return state


def check(state: dict, module: str, doctype: str | None = None) -> str | None:
	"""Return an error message if the action is not allowed, else None."""
	if module == CORE:
		return None
	label = MODULES.get(module, module)
	if module not in state["modules"]:
		return f"The {label} module is not part of this school's subscription."
	if not state["writable"] and doctype not in ALWAYS_WRITABLE:
		return state["message"]
	return None
