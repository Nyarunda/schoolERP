"""Boarding: dormitory rules and exeat (leave-out) passes (no Frappe)."""

from datetime import datetime, timedelta

DORM_GENDER = {"Boys": {"Male"}, "Girls": {"Female"}, "Mixed": {"Male", "Female"}}

EXEAT_STATUSES = ["Requested", "Approved", "Out", "Returned", "Rejected", "Cancelled"]
EXEAT_TRANSITIONS = {
	"Requested": {"Approved", "Rejected", "Cancelled"},
	"Approved": {"Out", "Cancelled"},
	"Out": {"Returned"},
	"Returned": set(),
	"Rejected": set(),
	"Cancelled": set(),
}
EXEAT_OPEN = {"Requested", "Approved", "Out"}
OVERDUE_GRACE_MINUTES = 60


def gender_problem(dorm_gender: str | None, student_gender: str | None) -> str | None:
	allowed = DORM_GENDER.get(dorm_gender or "Mixed", {"Male", "Female"})
	if not student_gender:
		return "Set the learner's gender before allocating a bed"
	if student_gender not in allowed:
		return f"A {student_gender.lower()} learner can't be placed in a {dorm_gender} dormitory"
	return None


def capacity_problem(capacity: int | None, occupied_by_others: int) -> str | None:
	if capacity and occupied_by_others >= int(capacity):
		return f"The dormitory is full ({occupied_by_others} of {capacity} beds taken)"
	return None


def occupancy(capacity: int | None, occupied: int) -> dict:
	cap = int(capacity or 0)
	return {"capacity": cap, "occupied": occupied, "free": max(cap - occupied, 0),
			"percent": round(occupied / cap * 100, 1) if cap else 0.0}


def exeat_transition_problem(old: str | None, new: str) -> str | None:
	if new not in EXEAT_STATUSES:
		return f"Unknown status {new}"
	if old is None or old == new:
		return None
	if new not in EXEAT_TRANSITIONS.get(old, set()):
		return f"An exeat that is {old} can't be marked {new}"
	return None


def _dt(value) -> datetime:
	return value if isinstance(value, datetime) else datetime.fromisoformat(str(value)[:19])


def is_overdue(expected_return, now: datetime, grace_minutes: int = OVERDUE_GRACE_MINUTES) -> bool:
	return now > _dt(expected_return) + timedelta(minutes=grace_minutes)


def minutes_late(expected_return, actual_return) -> int:
	"""0 when back on time (or early)."""
	late = (_dt(actual_return) - _dt(expected_return)).total_seconds() / 60
	return int(late) if late > 0 else 0
