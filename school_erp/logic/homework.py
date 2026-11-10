"""Homework: due-date wording, completion and what parents see (no Frappe)."""

from datetime import date, timedelta

DONE = {"Submitted", "Late", "Excused"}


def _d(value) -> date:
	return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def due_label(due, today: date) -> str:
	days = (_d(due) - today).days
	if days < 0:
		return "Overdue" if days < -1 else "Was due yesterday"
	if days == 0:
		return "Due today"
	if days == 1:
		return "Due tomorrow"
	return f"Due in {days} days"


def completion(statuses: list[str | None]) -> dict:
	"""Submission statuses of a class -> counts and % done (Excused counts as done, never as missing)."""
	total = len(statuses)
	done = sum(1 for s in statuses if s in DONE)
	return {"total": total, "done": done, "pending": total - done, "percent": round(done / total * 100, 1) if total else 0.0}


def for_parents(items: list[dict], today: date, days_back: int = 7) -> list[dict]:
	"""Published homework a parent should see: anything not yet due, plus the last week's, soonest first."""
	cutoff = today - timedelta(days=days_back)
	shown = [i for i in items if i.get("status") == "Published" and _d(i["due_date"]) >= cutoff]
	shown.sort(key=lambda i: (_d(i["due_date"]) < today, abs((_d(i["due_date"]) - today).days)))
	return shown
