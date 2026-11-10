"""Framework-free tests for admission application rules (no bench needed)."""

from school_erp.logic.admissions import funnel, requirement_problem, transition_problem


def test_transitions():
	assert transition_problem(None, "Received") is None
	assert transition_problem("Received", "Received") is None
	assert transition_problem("Received", "Interview Scheduled") is None
	assert transition_problem("Offered", "Accepted") is None
	assert "can't be marked" in transition_problem("Received", "Accepted")
	assert "can't be marked" in transition_problem("Admitted", "Withdrawn")
	assert transition_problem("Rejected", "Under Review") is None
	assert transition_problem("Bogus", "Nope").startswith("Unknown")


def test_admitted_only_through_admit():
	assert "Admit as Student" in transition_problem("Offered", "Admitted")
	assert transition_problem("Offered", "Admitted", admitting=True) is None
	assert transition_problem("Accepted", "Admitted", admitting=True) is None
	assert transition_problem("Received", "Admitted", admitting=True)


def test_requirements():
	assert requirement_problem("Interview Scheduled", {}) == "Set the interview date and time"
	assert requirement_problem("Interview Scheduled", {"interview_date": "2026-11-20 09:00"}) is None
	assert requirement_problem("Rejected", {"decision_notes": "  "})
	assert requirement_problem("Rejected", {"decision_notes": "Class full"}) is None
	assert requirement_problem("Offered", {}) is None


def test_funnel():
	rows = [{"status": s} for s in ["Received", "Received", "Offered", "Admitted", "Admitted", "Rejected", "Withdrawn", "?"]]
	f = funnel(rows)
	assert f["total"] == 7 and f["open"] == 3
	assert f["counts"]["Admitted"] == 2
	assert f["conversion"] == 50.0
	assert funnel([])["conversion"] == 0.0
