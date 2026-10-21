"""Assembles the numbers shown on a parent's fee statement."""


def _r(x):
	return round(float(x or 0), 2)


def build_ledger(opening: float, vouchers: list[dict]) -> dict:
	"""
	vouchers: [{date, details, reference, kind ('charge'|'payment'|'adjustment'), debit, credit}] in date order.
	Returns rows with running balance and the period totals.
	"""
	balance = _r(opening)
	rows, charged, paid, adjusted = [], 0.0, 0.0, 0.0
	for v in vouchers:
		debit, credit = _r(v.get("debit")), _r(v.get("credit"))
		balance = _r(balance + debit - credit)
		kind = v.get("kind") or ("charge" if debit >= credit else "payment")
		if kind == "charge":
			charged += debit - credit
		elif kind == "payment":
			paid += credit - debit
		else:
			adjusted += debit - credit
		rows.append(dict(v, debit=debit, credit=credit, balance=balance, kind=kind))
	return {
		"opening": _r(opening),
		"rows": rows,
		"charged": _r(charged),
		"paid": _r(paid),
		"adjusted": _r(adjusted),
		"closing": balance,
	}


def breakdown_rows(period_lines: list[dict], arrears: float, unallocated_credit: float) -> dict:
	"""
	period_lines: [{fee_type, billed, paid, outstanding, priority}] across the period's invoices
	Groups by fee type and adds arrears / advance rows.
	"""
	grouped: dict[str, dict] = {}
	for l in period_lines:
		g = grouped.setdefault(l["fee_type"], {"fee_type": l["fee_type"], "billed": 0.0, "paid": 0.0, "outstanding": 0.0, "priority": l.get("priority", 50)})
		g["billed"] += l["billed"]
		g["paid"] += l["paid"]
		g["outstanding"] += l["outstanding"]
	rows = sorted(grouped.values(), key=lambda g: (g["priority"], g["fee_type"]))
	for g in rows:
		for k in ("billed", "paid", "outstanding"):
			g[k] = _r(g[k])
	extra = []
	if _r(arrears) > 0:
		extra.append({"fee_type": "Balance from earlier terms", "billed": None, "paid": None, "outstanding": _r(arrears), "note": True})
	if _r(unallocated_credit) > 0:
		extra.append({"fee_type": "Advance payment not yet applied", "billed": None, "paid": None, "outstanding": -_r(unallocated_credit), "note": True})
	total = {
		"billed": _r(sum(g["billed"] for g in rows)),
		"paid": _r(sum(g["paid"] for g in rows)),
		"outstanding": _r(sum(g["outstanding"] for g in rows) + arrears - unallocated_credit),
	}
	return {"rows": rows, "extra": extra, "total": total}


def status_line(closing: float, due_date_label: str | None, money) -> dict:
	if closing > 0.004:
		text = f"Please pay {money(closing)}" + (f" by {due_date_label}" if due_date_label else "")
		return {"tone": "due", "label": "Balance Due", "text": text}
	if closing < -0.004:
		return {"tone": "credit", "label": "Credit Balance", "text": f"You have a credit of {money(-closing)}. It will be used for the next fees."}
	return {"tone": "clear", "label": "Fully Paid", "text": "All fees are paid. Thank you!"}
