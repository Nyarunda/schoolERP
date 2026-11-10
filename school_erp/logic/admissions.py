"""Admission applications: which status may follow which, and what each status needs (no Frappe)."""

STATUSES = ["Received", "Under Review", "Interview Scheduled", "Offered", "Accepted", "Admitted", "Rejected", "Withdrawn"]

TRANSITIONS = {
	"Received": {"Under Review", "Interview Scheduled", "Offered", "Rejected", "Withdrawn"},
	"Under Review": {"Interview Scheduled", "Offered", "Rejected", "Withdrawn"},
	"Interview Scheduled": {"Under Review", "Offered", "Rejected", "Withdrawn"},
	"Offered": {"Accepted", "Admitted", "Rejected", "Withdrawn"},
	"Accepted": {"Admitted", "Withdrawn"},
	"Admitted": set(),
	"Rejected": {"Under Review"},  # reconsidered
	"Withdrawn": {"Under Review"},  # came back
}
# Admitted is reached only through "Admit as Student", which creates the Student record
ADMIT_FROM = {"Offered", "Accepted"}
OPEN = {"Received", "Under Review", "Interview Scheduled", "Offered", "Accepted"}


def transition_problem(old: str | None, new: str, *, admitting: bool = False) -> str | None:
	"""None when an application may move from old to new, else the reason."""
	if new not in STATUSES:
		return f"Unknown status {new}"
	if old is None or old == new:
		return None
	if new == "Admitted" and not admitting:
		return "Use 'Admit as Student' to admit an applicant"
	if new not in TRANSITIONS.get(old, set()):
		return f"An application that is {old} can't be marked {new}"
	return None


def requirement_problem(status: str, doc: dict) -> str | None:
	"""What a status needs filled in before it can be saved."""
	if status == "Interview Scheduled" and not doc.get("interview_date"):
		return "Set the interview date and time"
	if status == "Rejected" and not (doc.get("decision_notes") or "").strip():
		return "Write the reason in Decision Notes before rejecting (it is not sent to the parent)"
	return None


def funnel(rows: list[dict]) -> dict:
	"""rows: [{status}] -> counts per status plus conversion: admitted / decided (admitted + rejected + withdrawn)."""
	counts = {s: 0 for s in STATUSES}
	for r in rows:
		if r.get("status") in counts:
			counts[r["status"]] += 1
	decided = counts["Admitted"] + counts["Rejected"] + counts["Withdrawn"]
	return {"counts": counts, "total": sum(counts.values()), "open": sum(counts[s] for s in OPEN),
			"conversion": round(counts["Admitted"] / decided * 100, 1) if decided else 0.0}
