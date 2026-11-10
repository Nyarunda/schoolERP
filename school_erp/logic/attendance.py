"""Class attendance arithmetic (no Frappe: unit-tested on its own)."""

STATUSES = ("Present", "Absent", "Late", "Excused")
# Late students are in school, so they count as attending; Excused (sick note, school trip) is still not in class.
ATTENDING = ("Present", "Late")


def summarise(statuses) -> dict:
	statuses = list(statuses)
	counts = {s.lower(): sum(1 for x in statuses if x == s) for s in STATUSES}
	total = len(statuses)
	attending = counts["present"] + counts["late"]
	counts["total_students"] = total
	counts["attendance_percent"] = round(attending / total * 100, 1) if total else 0.0
	return counts


def rate(attended: int, marked: int):
	"""Attendance % over several days; None when nothing was marked."""
	return round(attended / marked * 100, 1) if marked else None


def newly_absent(old: dict, new: dict) -> list[str]:
	"""Students marked Absent now who were not absent in the last saved register (so a parent is told once)."""
	return [st for st, status in new.items() if status == "Absent" and old.get(st) != "Absent"]
