"""Framework-free tests for library rules (no bench needed)."""

from datetime import date

from school_erp.logic.library import (
	copy_counts,
	days_overdue,
	due_date_for,
	fine_for,
	limit_problem,
	reminder_due,
	renew_problem,
)


def test_due_and_overdue():
	assert due_date_for("2026-11-01", 14) == date(2026, 11, 15)
	assert due_date_for(date(2026, 11, 1), 0) == date(2026, 11, 2)
	assert days_overdue("2026-11-15", "2026-11-15") == 0
	assert days_overdue("2026-11-15", date(2026, 11, 20)) == 5
	assert days_overdue("2026-11-15", "2026-11-10") == 0


def test_fines():
	assert fine_for(5, 10) == 50
	assert fine_for(5, 10, grace_days=2) == 30
	assert fine_for(1, 10, grace_days=3) == 0
	assert fine_for(100, 10, cap=500) == 500
	assert fine_for(3, 0) == 0


def test_limits_and_renewals():
	assert limit_problem(1, 2, "Amani") is None
	assert "limit 2" in limit_problem(2, 2, "Amani")
	assert limit_problem(9, 0, "Teacher") is None  # 0 = no limit
	today = date(2026, 11, 10)
	assert renew_problem("On Loan", "2026-11-12", today, 0, 1) is None
	assert "renewed" in renew_problem("On Loan", "2026-11-12", today, 1, 1)
	assert "overdue" in renew_problem("On Loan", "2026-11-09", today, 0, 1)
	assert renew_problem("Returned", "2026-11-12", today, 0, 1)


def test_copy_counts():
	assert copy_counts(["Available", "On Loan", "Lost", "Available", "Withdrawn"]) == {"total": 3, "available": 2, "on_loan": 1}


def test_reminders():
	today = date(2026, 11, 10)
	assert not reminder_due(0, None, today)
	assert reminder_due(1, None, today)
	assert not reminder_due(5, "2026-11-08", today)
	assert reminder_due(9, "2026-11-03", today)
