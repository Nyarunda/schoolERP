"""Grading, ranking and report-card maths (no Frappe)."""

# Default scales installed by Run School Setup
CBC_BANDS = [
	(80, 100, "EE", 4, "Exceeding Expectations"),
	(50, 79.99, "ME", 3, "Meeting Expectations"),
	(30, 49.99, "AE", 2, "Approaching Expectations"),
	(0, 29.99, "BE", 1, "Below Expectations"),
]

KCSE_BANDS = [
	(80, 100, "A", 12, "Excellent"), (75, 79.99, "A-", 11, "Very good"), (70, 74.99, "B+", 10, "Very good"),
	(65, 69.99, "B", 9, "Good"), (60, 64.99, "B-", 8, "Good"), (55, 59.99, "C+", 7, "Fair"),
	(50, 54.99, "C", 6, "Fair"), (45, 49.99, "C-", 5, "Average"), (40, 44.99, "D+", 4, "Below average"),
	(35, 39.99, "D", 3, "Weak"), (30, 34.99, "D-", 2, "Weak"), (0, 29.99, "E", 1, "Poor"),
]


def bands_from_rows(rows: list[dict]) -> list[tuple]:
	return sorted(((float(r["min_score"]), float(r["max_score"]), r["grade"], float(r.get("points") or 0), r.get("remark") or "")
				   for r in rows), key=lambda b: -b[0])


def grade_for(percent: float | None, bands: list[tuple]) -> dict:
	"""bands: [(min, max, grade, points, remark)] in any order. Percent is rounded to 2dp before matching,
	so 79.995 counts as 80 and gaps like 79.99..80 never fall through."""
	if percent is None:
		return {"grade": "", "points": 0.0, "remark": ""}
	p = round(float(percent), 2)
	for lo, hi, grade, points, remark in sorted(bands, key=lambda b: -b[0]):
		if p >= lo:
			return {"grade": grade, "points": float(points), "remark": remark}
	return {"grade": "", "points": 0.0, "remark": ""}


def competition_rank(scores: dict[str, float | None]) -> dict[str, int]:
	"""Standard competition ranking (1, 2, 2, 4). Students with no score are not ranked."""
	ordered = sorted(((k, v) for k, v in scores.items() if v is not None), key=lambda kv: -kv[1])
	ranks, prev, prev_rank = {}, None, 0
	for i, (k, v) in enumerate(ordered, 1):
		if prev is None or round(v, 4) != round(prev, 4):
			prev_rank = i
		ranks[k] = prev_rank
		prev = v
	return ranks


def build_results(marks: dict[str, dict[str, dict]], out_of: dict[str, float], bands: list[tuple]) -> dict[str, dict]:
	"""
	marks:  student -> subject -> {"marks": float|None, "absent": bool}
	out_of: subject -> maximum marks
	Returns student -> {subjects: {subject: {marks, out_of, percent, grade, points, remark}}, total_marks,
						total_out_of, mean_percent, mean_grade, mean_points, sat}
	Absent subjects are shown but excluded from the totals; a student who sat nothing has no mean.
	"""
	out = {}
	for student, subs in marks.items():
		rows, total, total_max, points = {}, 0.0, 0.0, []
		for subject, m in subs.items():
			mx = float(out_of.get(subject) or 100)
			if m.get("absent") or m.get("marks") is None:
				rows[subject] = {"marks": None, "out_of": mx, "percent": None, "grade": "ABS" if m.get("absent") else "", "points": 0.0, "remark": "Absent" if m.get("absent") else ""}
				continue
			val = float(m["marks"])
			pct = round(val / mx * 100, 2) if mx else 0.0
			g = grade_for(pct, bands)
			rows[subject] = {"marks": val, "out_of": mx, "percent": pct, **g}
			total += val
			total_max += mx
			points.append(g["points"])
		mean = round(total / total_max * 100, 2) if total_max else None
		mg = grade_for(mean, bands)
		out[student] = {
			"subjects": rows, "total_marks": round(total, 2), "total_out_of": round(total_max, 2),
			"mean_percent": mean, "mean_grade": mg["grade"] if mean is not None else "",
			"mean_points": round(sum(points) / len(points), 2) if points else 0.0, "sat": len(points),
		}
	return out


def subject_positions(results: dict[str, dict]) -> dict[str, dict[str, int]]:
	"""subject -> student -> position by percent within the group."""
	subjects = {s for r in results.values() for s in r["subjects"]}
	return {sub: competition_rank({st: r["subjects"].get(sub, {}).get("percent") for st, r in results.items()}) for sub in subjects}


def auto_remark(mean_percent: float | None, previous: float | None = None) -> str:
	"""A sensible default class-teacher remark the teacher can edit."""
	if mean_percent is None:
		return "Did not sit the exam."
	if mean_percent >= 80:
		base = "Excellent work. Keep it up."
	elif mean_percent >= 65:
		base = "Very good performance. Aim higher."
	elif mean_percent >= 50:
		base = "Good effort. There is room to improve."
	elif mean_percent >= 35:
		base = "Fair. More effort and consistency needed."
	else:
		base = "Needs a lot of support and hard work. Please see the class teacher."
	if previous is not None:
		diff = round(mean_percent - previous, 1)
		if diff >= 3:
			base += f" Improved by {diff:g}% since the last exam."
		elif diff <= -3:
			base += f" Dropped by {abs(diff):g}% since the last exam."
	return base
