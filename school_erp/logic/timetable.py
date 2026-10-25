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


def hm(t) -> str:
	"""timedelta / time / 'H:MM:SS' -> 'HH:MM'"""
	parts = str(t or "0:00").split(":")
	return f"{int(parts[0]):02d}:{parts[1][:2]}"


SESSION_NAMES = {2: "Double", 3: "Triple"}


def session_blocks(slots: list[dict], periods: list[dict]) -> list[dict]:
	"""Merge back-to-back lessons of the same subject and teacher on a day into one session.

	Periods are adjacent only when nothing (not even a break) sits between them in the bell schedule.
	slots: dicts with day, period, subject, teacher. periods: dicts with name, sequence, start_time, end_time.
	Returns blocks in day/time order: {day, subject, teacher, slots, start, end, size}.
	"""
	order = {p["name"]: i for i, p in enumerate(sorted(periods, key=lambda p: p.get("sequence") or 0))}
	by_name = {p["name"]: p for p in periods}
	day_rank = {d: i for i, d in enumerate(DAYS)}
	lessons = sorted((s for s in slots if s.get("subject") and s.get("period") in order),
					 key=lambda s: (day_rank.get(s["day"], 9), order[s["period"]]))
	blocks = []
	for s in lessons:
		last = blocks[-1] if blocks else None
		if (last and last["day"] == s["day"] and last["subject"] == s["subject"]
				and (last["teacher"] or "") == (s.get("teacher") or "")
				and order[s["period"]] == order[last["slots"][-1]["period"]] + 1):
			last["slots"].append(s)
		else:
			blocks.append({"day": s["day"], "subject": s["subject"], "teacher": s.get("teacher") or "", "slots": [s]})
	for b in blocks:
		b["size"] = len(b["slots"])
		b["start"] = hm(by_name[b["slots"][0]["period"]]["start_time"])
		b["end"] = hm(by_name[b["slots"][-1]["period"]]["end_time"])
	return blocks


def session_labels(slots: list[dict], periods: list[dict]) -> dict:
	"""{id(slot): (time, session)}: a single lesson shows its period's time; every lesson in a double shows the
	whole session's time and 'Double 1/2', 'Double 2/2'."""
	by_name = {p["name"]: p for p in periods}
	out = {}
	for s in slots:
		p = by_name.get(s.get("period"))
		out[id(s)] = (f"{hm(p['start_time'])}-{hm(p['end_time'])}" if p else "", "")
	for b in session_blocks(slots, periods):
		if b["size"] > 1:
			name = SESSION_NAMES.get(b["size"], f"{b['size']} periods")
			for i, s in enumerate(b["slots"], 1):
				out[id(s)] = (f"{b['start']}-{b['end']}", f"{name} {i}/{b['size']}")
	return out
