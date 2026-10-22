"""Year-end promotion rules (no Frappe)."""


def stream_suffix(stream: str | None, school_class: str | None) -> str | None:
	"""'Grade 4 East' in class 'Grade 4' -> 'East'."""
	if not stream:
		return None
	if school_class and stream.startswith(school_class + " "):
		return stream[len(school_class) + 1:]
	return stream.split(" ")[-1]


def plan_student(current_class: str, current_stream: str | None, next_class: str | None) -> dict:
	"""Default action for one student: promote to next class (same stream name) or graduate if there is no next class."""
	if not next_class:
		return {"action": "Graduate", "new_class": None, "new_stream": None}
	suffix = stream_suffix(current_stream, current_class)
	return {"action": "Promote", "new_class": next_class, "new_stream": f"{next_class} {suffix}" if suffix else None}


def apply_action(action: str, current_class: str, current_stream: str | None, next_class: str | None) -> dict:
	"""Where a student ends up for a chosen action."""
	if action == "Promote":
		return plan_student(current_class, current_stream, next_class) if next_class else {"action": "Graduate", "new_class": None, "new_stream": None}
	if action == "Repeat":
		return {"action": "Repeat", "new_class": current_class, "new_stream": current_stream}
	return {"action": action, "new_class": None, "new_stream": None}


def summarize(items: list[dict]) -> dict:
	out = {"total": len(items), "promote": 0, "graduate": 0, "repeat": 0, "left": 0, "with_balance": 0, "balance": 0.0}
	for i in items:
		key = {"Promote": "promote", "Graduate": "graduate", "Repeat": "repeat", "Left School": "left"}[i["action"]]
		out[key] += 1
		if (i.get("balance") or 0) > 0.004:
			out["with_balance"] += 1
			out["balance"] += float(i["balance"])
	out["balance"] = round(out["balance"], 2)
	return out
