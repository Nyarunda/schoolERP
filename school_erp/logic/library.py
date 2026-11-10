"""Library: due dates, overdue fines, loan limits and copy counts (no Frappe)."""

from datetime import date, timedelta

COPY_STATUSES = ["Available", "On Loan", "Lost", "Damaged", "Withdrawn"]
IN_STOCK = {"Available", "On Loan"}  # copies the library still has


def _d(value) -> date:
	return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def due_date_for(issue_date, loan_days: int) -> date:
	return _d(issue_date) + timedelta(days=max(int(loan_days or 0), 1))


def days_overdue(due, on) -> int:
	return max((_d(on) - _d(due)).days, 0)


def fine_for(days_late: int, per_day: float, grace_days: int = 0, cap: float = 0) -> float:
	"""Fine for a late return: per day after the grace days, never more than the cap (0 = no cap)."""
	chargeable = max(int(days_late) - int(grace_days or 0), 0)
	fine = round(chargeable * float(per_day or 0), 2)
	return min(fine, float(cap)) if cap else fine


def limit_problem(open_loans: int, max_loans: int, borrower: str) -> str | None:
	if max_loans and open_loans >= int(max_loans):
		return f"{borrower} already has {open_loans} book(s) out (limit {max_loans}). Return one first."
	return None


def renew_problem(status: str, due, today, renewals: int, max_renewals: int) -> str | None:
	if status != "On Loan":
		return "Only a book that is out can be renewed"
	if days_overdue(due, today):
		return "The book is overdue: return it (and settle any fine) instead of renewing"
	if max_renewals is not None and int(renewals or 0) >= int(max_renewals):
		return f"This loan has already been renewed {renewals} time(s)"
	return None


def copy_counts(statuses: list[str]) -> dict:
	return {"total": sum(1 for s in statuses if s in IN_STOCK), "available": sum(1 for s in statuses if s == "Available"),
			"on_loan": sum(1 for s in statuses if s == "On Loan")}


def reminder_due(days_late: int, last_reminder, today, every_days: int = 7) -> bool:
	"""First reminder the day after the due date, then every `every_days` days."""
	if days_late <= 0:
		return False
	return last_reminder is None or (_d(today) - _d(last_reminder)).days >= every_days
