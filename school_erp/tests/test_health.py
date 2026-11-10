"""Framework-free tests for sick bay, visitor and gate pass rules (no bench needed)."""

from datetime import datetime

from school_erp.logic.health import frequent_visitors, has_fever, minutes_between, order_problem, parent_must_know, temperature_problem


def test_temperature():
	assert temperature_problem(None) is None
	assert temperature_problem(36.8) is None
	assert "Celsius" in temperature_problem(98.6)
	assert temperature_problem(29) is not None
	assert has_fever(37.5) and not has_fever(37.4) and not has_fever(None)


def test_parent_must_know():
	assert parent_must_know("Sent home")
	assert parent_must_know("Referred to hospital")
	assert not parent_must_know("Returned to class", 36.9)
	assert parent_must_know("Returned to class", 38.2)


def test_frequent_visitors():
	rows = [{"student": "A", "student_name": "Ann"}] * 3 + [{"student": "B", "student_name": "Ben"}] * 4 + [{"student": "C", "student_name": "Cy"}]
	assert [(r["student"], r["visits"]) for r in frequent_visitors(rows)] == [("B", 4), ("A", 3)]


def test_times():
	t0 = datetime(2026, 11, 10, 9, 0)
	assert minutes_between(t0, "2026-11-10 10:30:00") == 90
	assert minutes_between(t0, None) is None
	assert order_problem(t0, datetime(2026, 11, 10, 8, 0)) == "The time out is before the time in"
	assert order_problem(t0, None) is None
