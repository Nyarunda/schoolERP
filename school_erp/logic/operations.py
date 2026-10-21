"""Framework-free rules for leave, expense approvals and vehicle checks."""

from datetime import date, timedelta

# ----------------------------------------------------------------------------- leave


def leave_days(from_date: date, to_date: date, include_weekends: bool = False, holidays: set[date] | frozenset = frozenset()) -> float:
	"""Working days between two dates, inclusive. Weekends (Sat/Sun) and holidays are skipped unless include_weekends."""
	if to_date < from_date:
		return 0.0
	days, d = 0, from_date
	while d <= to_date:
		if include_weekends or (d.weekday() < 5 and d not in holidays):
			days += 1
		d += timedelta(days=1)
	return float(days)


def ranges_overlap(a_from: date, a_to: date, b_from: date, b_to: date) -> bool:
	return a_from <= b_to and b_from <= a_to


def leave_problems(app: dict, leave_type: dict, staff: dict, taken_days: float, overlapping: list[str],
				   reliever_busy: bool = False) -> list[str]:
	"""Validation messages for a leave application.

	app:        {from_date, to_date, total_days, reliever, attachment}
	leave_type: {days_per_year, requires_reliever, requires_attachment, gender, applies_to, max_days_per_application}
	staff:      {name, gender, staff_type}
	taken_days: approved + pending days already used this year for this type (excluding this application)
	overlapping: names of the staff member's other pending/approved leave that overlaps
	"""
	errors = []
	if app["to_date"] < app["from_date"]:
		errors.append("The end date is before the start date.")
	if app["total_days"] <= 0 and not errors:
		errors.append("The selected dates contain no working days.")
	g = leave_type.get("gender") or "All"
	if g != "All" and staff.get("gender") and staff["gender"] != g:
		errors.append(f"This leave type is only for {g.lower()} staff.")
	applies = leave_type.get("applies_to") or "All"
	if applies == "Teaching" and staff.get("staff_type") != "Teaching":
		errors.append("This leave type is only for teaching staff.")
	if applies == "Non-Teaching" and staff.get("staff_type") == "Teaching":
		errors.append("This leave type is only for non-teaching staff.")
	mx = int(leave_type.get("max_days_per_application") or 0)
	if mx and app["total_days"] > mx:
		errors.append(f"At most {mx} days can be taken in one application.")
	entitled = int(leave_type.get("days_per_year") or 0)
	if entitled and taken_days + app["total_days"] > entitled:
		left = max(entitled - taken_days, 0)
		errors.append(f"Only {left:g} day(s) of this leave remain this year; {app['total_days']:g} requested.")
	if leave_type.get("requires_reliever") and not app.get("reliever"):
		errors.append("A reliever is required for this leave type.")
	if app.get("reliever") and app["reliever"] == staff.get("name"):
		errors.append("You cannot be your own reliever.")
	if reliever_busy:
		errors.append("The chosen reliever is on leave during these dates.")
	if leave_type.get("requires_attachment") and not app.get("attachment"):
		errors.append("Attach a supporting document (e.g. doctor's note).")
	if overlapping:
		errors.append(f"These dates overlap with leave already applied for: {', '.join(overlapping)}.")
	return errors


# ----------------------------------------------------------------------------- expense approvals

FIRST, FINAL = "First", "Final"


def levels_required(amount: float, single_limit: float) -> int:
	"""1 approval up to the limit, 2 above it. A limit of 0 means every expense needs 2."""
	return 1 if single_limit and amount <= single_limit else 2


def next_level(levels: int, approvals: list[dict]) -> str | None:
	"""Which approval level is outstanding, given approvals [{level, action}]. None = fully approved."""
	done = {a["level"] for a in approvals if a.get("action") == "Approved"}
	if FIRST not in done:
		return FIRST
	if levels >= 2 and FINAL not in done:
		return FINAL
	return None


def approval_error(user: str, requester: str, level: str, user_roles: set[str], level_role: str,
				   approvals: list[dict], is_admin: bool = False) -> str | None:
	"""Why this user may not approve at this level, or None if they may."""
	if user == requester and not is_admin:
		return "You cannot approve your own expense."
	if any(a.get("user") == user and a.get("action") == "Approved" for a in approvals) and not is_admin:
		return "You have already approved this expense; a different person must give the next approval."
	if level_role not in user_roles and not is_admin:
		return f"The {level.lower()} approval must be given by a {level_role}."
	return None


def status_for(levels: int, approvals: list[dict]) -> str:
	if any(a.get("action") == "Rejected" for a in approvals):
		return "Rejected"
	nxt = next_level(levels, approvals)
	return {FIRST: "Pending Approval", FINAL: "Pending Final Approval", None: "Approved"}[nxt]


# ----------------------------------------------------------------------------- vehicles

DEFAULT_CHECKLIST = [
	"Tyres (pressure & condition)",
	"Brakes",
	"Lights & indicators",
	"Seat belts",
	"Doors & emergency exit",
	"Mirrors",
	"Wipers & windscreen",
	"Horn",
	"First aid kit",
	"Fire extinguisher",
	"Engine oil & coolant",
	"Bus clean inside",
]


def vehicle_problems(checklist: list[dict], fit_to_drive: bool, today: date, insurance_expiry: date | None = None,
					 inspection_expiry: date | None = None, license_expiry: date | None = None) -> list[str]:
	"""Everything the transport manager should hear about before the bus leaves."""
	problems = [f"{c['item']}: NOT OK{(' - ' + c['remarks']) if c.get('remarks') else ''}" for c in checklist if not c.get("ok")]
	if not fit_to_drive:
		problems.append("Driver has not declared fitness to drive")
	for label, d in (("Insurance", insurance_expiry), ("Inspection", inspection_expiry), ("Driving licence", license_expiry)):
		if d and d < today:
			problems.append(f"{label} expired on {d:%d %b %Y}")
	return problems
