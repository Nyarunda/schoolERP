"""Framework-free tests for homework rules (no bench needed)."""

from datetime import date

from school_erp.logic.homework import completion, due_label, for_parents

TODAY = date(2026, 11, 10)


def test_due_label():
	assert due_label("2026-11-10", TODAY) == "Due today"
	assert due_label(date(2026, 11, 11), TODAY) == "Due tomorrow"
	assert due_label("2026-11-15", TODAY) == "Due in 5 days"
	assert due_label("2026-11-09", TODAY) == "Was due yesterday"
	assert due_label("2026-11-01", TODAY) == "Overdue"


def test_completion():
	assert completion(["Submitted", "Late", "Excused", "Pending", None]) == {"total": 5, "done": 3, "pending": 2, "percent": 60.0}
	assert completion([])["percent"] == 0.0


def test_for_parents_upcoming_first_then_recent():
	items = [
		{"name": "old", "status": "Published", "due_date": "2026-10-20"},
		{"name": "draft", "status": "Draft", "due_date": "2026-11-12"},
		{"name": "past", "status": "Published", "due_date": "2026-11-08"},
		{"name": "later", "status": "Published", "due_date": "2026-11-14"},
		{"name": "soon", "status": "Published", "due_date": "2026-11-11"},
		{"name": "closed", "status": "Closed", "due_date": "2026-11-11"},
	]
	assert [i["name"] for i in for_parents(items, TODAY)] == ["soon", "later", "past"]
