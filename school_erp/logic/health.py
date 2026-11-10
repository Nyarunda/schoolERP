"""Sick bay, visitors and gate passes: vital-sign checks, who must be told, time on premises (no Frappe)."""

from datetime import datetime

OUTCOMES = ["Returned to class", "Rested in sick bay", "Sent home", "Referred to hospital"]
PARENT_MUST_KNOW = {"Sent home", "Referred to hospital"}
FEVER_FROM = 37.5


def temperature_problem(celsius) -> str | None:
	if celsius in (None, "", 0):
		return None
	t = float(celsius)
	if not 30 <= t <= 45:
		return f"{t:g} °C is not a body temperature: enter it in degrees Celsius"
	return None


def has_fever(celsius) -> bool:
	return bool(celsius) and float(celsius) >= FEVER_FROM


def parent_must_know(outcome: str | None, celsius=None) -> bool:
	"""Sent home or referred, always; a fever even if the learner went back to class."""
	return outcome in PARENT_MUST_KNOW or has_fever(celsius)


def frequent_visitors(rows: list[dict], min_visits: int = 3) -> list[dict]:
	"""[{student, student_name}] visits -> learners seen at least min_visits times, most visits first."""
	counts: dict[str, dict] = {}
	for r in rows:
		c = counts.setdefault(r["student"], {"student": r["student"], "student_name": r.get("student_name"), "visits": 0})
		c["visits"] += 1
	return sorted((c for c in counts.values() if c["visits"] >= min_visits), key=lambda c: (-c["visits"], c["student_name"] or ""))


def _dt(v) -> datetime:
	return v if isinstance(v, datetime) else datetime.fromisoformat(str(v)[:19])


def minutes_between(start, end) -> int | None:
	if not (start and end):
		return None
	return max(int((_dt(end) - _dt(start)).total_seconds() // 60), 0)


def order_problem(start, end, start_label="time in", end_label="time out") -> str | None:
	if start and end and _dt(end) < _dt(start):
		return f"The {end_label} is before the {start_label}"
	return None
