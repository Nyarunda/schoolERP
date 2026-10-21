"""Works out which fees a student is charged for a term."""

from .license import CATEGORY_MODULE

SERVICE_CATEGORIES = {"Transport", "Activity"}  # billed from their own masters, never from a fee structure


def structure_matches(structure: dict, student: dict) -> bool:
	if structure.get("school_class") and structure["school_class"] != student.get("school_class"):
		return False
	bt = structure.get("boarding_type") or "All"
	return bt == "All" or bt == (student.get("boarding_type") or "Day")


def _specificity(structure: dict) -> int:
	return (2 if structure.get("school_class") else 0) + (1 if (structure.get("boarding_type") or "All") != "All" else 0)


def compute_fee_lines(
	student: dict,
	structures: list[dict],
	fee_types: dict[str, dict],
	routes: dict[str, dict],
	activities: dict[str, dict],
	modules: list[str],
	once_billed: set[str] | frozenset = frozenset(),
) -> list[dict]:
	"""
	student:     {school_class, boarding_type, takes_lunch, transport_route, activities: [names], scholarship_percent}
	structures:  active fee structures for the term: {school_class, boarding_type, items: [{fee_type, amount, description}]}
	fee_types:   name -> {category, charge_basis, priority, discountable}
	routes:      name -> {fee_per_term, fee_type, is_active}
	activities:  name -> {fee_per_term, fee_type, is_active}
	modules:     licensed module codes
	once_billed: fee types with charge_basis "Once" already billed to this student

	Returns lines sorted by payment priority: {fee_type, category, amount, discount_percent, description}
	"""
	if "fees" not in modules:
		return []

	def allowed(fee_type):
		ft = fee_types.get(fee_type)
		if not ft:
			return False
		need = CATEGORY_MODULE.get(ft["category"])
		if need and need not in modules:
			return False
		if ft.get("charge_basis") == "Once" and fee_type in once_billed:
			return False
		return True

	scholarship = float(student.get("scholarship_percent") or 0)
	lines, seen = [], set()

	def add(fee_type, amount, description):
		amount = float(amount or 0)
		if amount <= 0 or fee_type in seen or not allowed(fee_type):
			return
		ft = fee_types[fee_type]
		seen.add(fee_type)
		lines.append(
			{
				"fee_type": fee_type,
				"category": ft["category"],
				"amount": round(amount, 2),
				"discount_percent": scholarship if ft.get("discountable") else 0.0,
				"description": description or fee_type,
				"priority": int(ft.get("priority") or 10),
			}
		)

	matching = sorted((s for s in structures if structure_matches(s, student)), key=_specificity, reverse=True)
	for s in matching:
		for item in s.get("items", []):
			ft = fee_types.get(item["fee_type"])
			if not ft or ft["category"] in SERVICE_CATEGORIES:
				continue
			if ft["category"] == "Lunch" and not student.get("takes_lunch"):
				continue
			add(item["fee_type"], item["amount"], item.get("description"))

	route = routes.get(student.get("transport_route") or "")
	if route and route.get("is_active", 1):
		add(route["fee_type"], route["fee_per_term"], f"Transport - {student['transport_route']}")

	for name in student.get("activities") or []:
		act = activities.get(name)
		if act and act.get("is_active", 1) and act.get("fee_type"):
			# several activities can share one fee type; key them apart
			key = act["fee_type"]
			if key in seen:
				_merge_activity(lines, key, act["fee_per_term"], name)
			else:
				add(key, act["fee_per_term"], f"{name}")

	lines.sort(key=lambda l: (l["priority"], l["fee_type"]))
	return lines


def _merge_activity(lines, fee_type, amount, name):
	for line in lines:
		if line["fee_type"] == fee_type:
			line["amount"] = round(line["amount"] + float(amount or 0), 2)
			line["description"] = f"{line['description']}, {name}"
			return


def net_amount(line: dict) -> float:
	return round(line["amount"] * (1 - (line.get("discount_percent") or 0) / 100.0), 2)


def summarize_run(students: list[dict]) -> dict:
	"""
	students: [{include, lines: [{fee_type, amount, discount_percent}]}]
	Totals over the included students: count, amount, and per fee type (students charged, amount).
	"""
	by_type: dict[str, dict] = {}
	total, count = 0.0, 0
	for s in students:
		if not s.get("include"):
			continue
		count += 1
		for line in s.get("lines") or []:
			amt = net_amount(line)
			total += amt
			row = by_type.setdefault(line["fee_type"], {"fee_type": line["fee_type"], "students": 0, "amount": 0.0,
														"priority": line.get("priority", 10)})
			row["students"] += 1
			row["amount"] = round(row["amount"] + amt, 2)
	rows = sorted(by_type.values(), key=lambda r: (r["priority"], r["fee_type"]))
	return {"students": count, "amount": round(total, 2), "by_fee_type": rows}


def describe_lines(lines: list[dict], fmt=lambda v: f"{v:,.0f}") -> str:
	"""'Tuition 25,000 · Lunch 6,000 (−50%)' for the student row."""
	parts = []
	for l in lines:
		txt = f"{l['fee_type']} {fmt(net_amount(l))}"
		if l.get("discount_percent"):
			txt += f" (-{l['discount_percent']:g}%)"
		parts.append(txt)
	return " · ".join(parts)
