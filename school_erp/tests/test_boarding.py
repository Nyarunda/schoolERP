"""Framework-free tests for dormitory and exeat rules (no bench needed)."""

from datetime import datetime

from school_erp.logic.boarding import (
	capacity_problem,
	exeat_transition_problem,
	gender_problem,
	is_overdue,
	minutes_late,
	occupancy,
)


def test_gender_rules():
	assert gender_problem("Boys", "Male") is None
	assert gender_problem("Mixed", "Female") is None
	assert "Girls" in gender_problem("Girls", "Male")
	assert gender_problem("Boys", None)


def test_capacity_and_occupancy():
	assert capacity_problem(40, 39) is None
	assert "full" in capacity_problem(40, 40)
	assert capacity_problem(0, 100) is None  # no capacity set: not enforced
	assert occupancy(40, 30) == {"capacity": 40, "occupied": 30, "free": 10, "percent": 75.0}
	assert occupancy(10, 12)["free"] == 0
	assert occupancy(None, 3)["percent"] == 0.0


def test_exeat_transitions():
	assert exeat_transition_problem(None, "Requested") is None
	assert exeat_transition_problem("Requested", "Approved") is None
	assert exeat_transition_problem("Approved", "Out") is None
	assert exeat_transition_problem("Out", "Returned") is None
	assert exeat_transition_problem("Requested", "Out")  # must be approved first
	assert exeat_transition_problem("Returned", "Out")
	assert exeat_transition_problem("Out", "Cancelled")  # already out: only coming back
	assert exeat_transition_problem("Out", "Bogus").startswith("Unknown")


def test_overdue_and_lateness():
	due = datetime(2026, 11, 15, 17, 0)
	assert not is_overdue(due, datetime(2026, 11, 15, 17, 59))
	assert is_overdue(due, datetime(2026, 11, 15, 18, 1))
	assert is_overdue("2026-11-15 17:00:00", datetime(2026, 11, 15, 17, 30), grace_minutes=15)
	assert minutes_late(due, datetime(2026, 11, 15, 16, 0)) == 0
	assert minutes_late(due, "2026-11-15 18:30:00") == 90
