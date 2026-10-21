"""Timetable checks."""

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def find_duplicate_slots(slots: list[dict]) -> list[str]:
	seen, errors = {}, []
	for i, s in enumerate(slots, 1):
		key = (s["day"], s["period"])
		if key in seen:
			errors.append(f"Row {i}: {s['day']} {s['period']} is already used in row {seen[key]}")
		else:
			seen[key] = i
	return errors


def find_teacher_clashes(slots: list[dict], other_slots: list[dict]) -> list[str]:
	"""other_slots: slots from other timetables in the same term, each with 'timetable' and 'teacher_name'."""
	busy = {}
	for o in other_slots:
		if o.get("teacher"):
			busy.setdefault((o["teacher"], o["day"], o["period"]), o)
	errors = []
	for i, s in enumerate(slots, 1):
		if not s.get("teacher"):
			continue
		hit = busy.get((s["teacher"], s["day"], s["period"]))
		if hit:
			who = hit.get("teacher_name") or s["teacher"]
			errors.append(f"Row {i}: {who} already teaches {hit['timetable']} on {s['day']} {s['period']}")
	return errors


def build_grid(slots: list[dict], periods: list[dict]) -> dict:
	"""Shape slots into rows (periods) x columns (days) for printing."""
	days = [d for d in DAYS if d != "Saturday" or any(s["day"] == "Saturday" for s in slots)]
	cell = {(s["day"], s["period"]): s for s in slots}
	rows = []
	for p in sorted(periods, key=lambda p: p.get("sequence") or 0):
		rows.append({"period": p, "cells": [cell.get((d, p["name"])) for d in days]})
	return {"days": days, "rows": rows}
