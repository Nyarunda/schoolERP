"""CBC competency-based assessment: rubric levels, strand and learning-area roll-ups (no Frappe).

CBC reports describe what a learner can do in each learning area. There are no marks, positions or mean grades:
a learner is placed on a rubric level per strand, strand levels are averaged per learning area and turned back
into a level with its descriptor.
"""

from collections import defaultdict

FOUR_LEVEL = "4-level (EE / ME / AE / BE)"
EIGHT_LEVEL = "8-level (EE1 - BE2)"

RUBRICS = {
	FOUR_LEVEL: [
		("EE", 4, "Exceeding Expectations"),
		("ME", 3, "Meeting Expectations"),
		("AE", 2, "Approaching Expectations"),
		("BE", 1, "Below Expectations"),
	],
	EIGHT_LEVEL: [
		("EE1", 8, "Exceeding Expectations (high)"),
		("EE2", 7, "Exceeding Expectations"),
		("ME1", 6, "Meeting Expectations (high)"),
		("ME2", 5, "Meeting Expectations"),
		("AE1", 4, "Approaching Expectations (high)"),
		("AE2", 3, "Approaching Expectations"),
		("BE1", 2, "Below Expectations (high)"),
		("BE2", 1, "Below Expectations"),
	],
}
ALL_LEVELS = [lvl for rows in RUBRICS.values() for lvl, _p, _d in rows]
BANDS = ("EE", "ME", "AE", "BE")


def rubric(name: str | None) -> list[tuple]:
	return RUBRICS.get(name or FOUR_LEVEL) or RUBRICS[FOUR_LEVEL]


def levels(name: str | None) -> list[str]:
	return [lvl for lvl, _p, _d in rubric(name)]


def points_for(level: str | None, rubric_name: str | None) -> int | None:
	for lvl, pts, _d in rubric(rubric_name):
		if lvl == level:
			return pts
	return None


def level_for(points: float | None, rubric_name: str | None) -> dict:
	"""Average points -> nearest rubric level (halves round up). 3.5 on the 4-level rubric is EE, 3.49 is ME."""
	if points is None:
		return {"level": "", "points": None, "descriptor": ""}
	rows = rubric(rubric_name)
	top, bottom = rows[0][1], rows[-1][1]
	nearest = int(min(max(float(points), bottom), top) + 0.5 + 1e-9)
	nearest = min(max(nearest, bottom), top)
	for lvl, pts, desc in rows:
		if pts == nearest:
			return {"level": lvl, "points": round(float(points), 2), "descriptor": desc}
	return {"level": "", "points": None, "descriptor": ""}


def band(level: str | None) -> str:
	"""EE1 / EE2 / EE -> EE: lets one report count both rubrics."""
	return (level or "")[:2] if (level or "")[:2] in BANDS else ""


def roll_up(results: list[dict], rubric_name: str | None) -> dict[str, dict[str, dict]]:
	"""results: [{student, subject, strand, level}] from submitted assessments (blank level = not assessed).

	Returns student -> subject -> {level, points, descriptor, strands, assessments}.
	Each strand counts once: its assessments are averaged first, then strands are averaged for the learning area, so
	a strand that was assessed five times does not outweigh one assessed once."""
	per_strand = defaultdict(list)  # (student, subject, strand) -> [points]
	for r in results:
		pts = points_for(r.get("level"), rubric_name)
		if pts is None:
			continue
		per_strand[(r["student"], r["subject"], r.get("strand") or "")].append(pts)
	per_subject = defaultdict(lambda: {"strand_means": [], "assessments": 0})
	for (student, subject, _strand), pts in per_strand.items():
		cell = per_subject[(student, subject)]
		cell["strand_means"].append(sum(pts) / len(pts))
		cell["assessments"] += len(pts)
	out: dict[str, dict[str, dict]] = defaultdict(dict)
	for (student, subject), cell in per_subject.items():
		mean = sum(cell["strand_means"]) / len(cell["strand_means"])
		out[student][subject] = {**level_for(mean, rubric_name), "strands": len(cell["strand_means"]),
								 "assessments": cell["assessments"]}
	return dict(out)


def distribution(level_values: list[str | None]) -> dict[str, int]:
	"""Count of learners per band (EE, ME, AE, BE) for a list of levels; blanks are ignored."""
	out = {b: 0 for b in BANDS}
	for lvl in level_values:
		b = band(lvl)
		if b:
			out[b] += 1
	return out


def distribution_text(level_values: list[str | None]) -> str:
	d = distribution(level_values)
	return " · ".join(f"{b} {n}" for b, n in d.items() if n)


def strengths_and_gaps(areas: dict[str, dict], names: dict[str, str] | None = None) -> tuple[str, str]:
	"""Learning areas at the top and bottom of a learner's profile, in words, for the report card."""
	names = names or {}
	scored = [(s, a["points"]) for s, a in areas.items() if a.get("points") is not None]
	if not scored:
		return "", ""
	best = max(p for _s, p in scored)
	worst = min(p for _s, p in scored)
	strong = sorted(names.get(s, s) for s, p in scored if p == best)
	weak = sorted(names.get(s, s) for s, p in scored if p == worst and p < best)
	return ", ".join(strong), ", ".join(weak)
