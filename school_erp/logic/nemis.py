"""Government learner IDs (NEMIS/KEMIS UPI, birth certificate, KNEC assessment number) and census maths. No Frappe."""

import re
from datetime import date

ID_PATTERN = re.compile(r"^[A-Z0-9/-]{4,20}$")

# What the Ministry's census and KNEC registration need from every learner
REQUIRED_FOR_CENSUS = ("upi_number", "birth_certificate_no", "date_of_birth", "gender")


def clean_id(value) -> str:
	"""'  ab 12 c3 ' -> 'AB12C3'. IDs are compared and stored without spaces, upper case."""
	return re.sub(r"\s+", "", str(value or "")).upper()


def id_problem(value, label) -> str | None:
	"""None when the ID looks usable, else a sentence for the user."""
	v = clean_id(value)
	if not v:
		return None
	if not ID_PATTERN.match(v):
		return f"{label} should be 4 to 20 letters or digits (got '{value}')"
	return None


def age_on(dob, on: date) -> int | None:
	if not dob:
		return None
	if isinstance(dob, str):
		dob = date.fromisoformat(dob[:10])
	years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
	return years if years >= 0 else None


def missing_items(row: dict) -> list[str]:
	"""Which census items a learner record still lacks."""
	labels = {"upi_number": "UPI", "birth_certificate_no": "Birth Cert", "date_of_birth": "Date of Birth", "gender": "Gender"}
	return [labels[k] for k in REQUIRED_FOR_CENSUS if not row.get(k)]


def class_summary(rows: list[dict]) -> list[dict]:
	"""rows: learners with school_class, gender, upi_number, birth_certificate_no, special_needs.
	Returns one row per class (in first-seen order) with boys/girls/total and data-quality counts."""
	out: dict[str, dict] = {}
	for r in rows:
		cls = r.get("school_class") or "(No class)"
		s = out.setdefault(cls, {"school_class": cls, "boys": 0, "girls": 0, "total": 0, "special_needs": 0,
								 "missing_upi": 0, "missing_birth_cert": 0, "complete": 0})
		s["total"] += 1
		if r.get("gender") == "Male":
			s["boys"] += 1
		elif r.get("gender") == "Female":
			s["girls"] += 1
		if r.get("special_needs"):
			s["special_needs"] += 1
		if not r.get("upi_number"):
			s["missing_upi"] += 1
		if not r.get("birth_certificate_no"):
			s["missing_birth_cert"] += 1
		if not missing_items(r):
			s["complete"] += 1
	for s in out.values():
		s["percent_complete"] = round(s["complete"] / s["total"] * 100, 1) if s["total"] else 0.0
	return list(out.values())


def age_gender_matrix(rows: list[dict], on: date) -> dict[int | None, dict[str, int]]:
	"""Age (completed years on `on`) -> {"Male": n, "Female": n}: the enrolment-by-age table of the school census."""
	out: dict[int | None, dict[str, int]] = {}
	for r in rows:
		age = age_on(r.get("date_of_birth"), on)
		cell = out.setdefault(age, {"Male": 0, "Female": 0})
		if r.get("gender") in cell:
			cell[r["gender"]] += 1
	return dict(sorted(out.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))
