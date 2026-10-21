"""Splitting money between fee types.

ERPNext tracks what is owed per invoice. Parents think per fee type ("I paid the transport").
We keep both views consistent:

* split_invoice_paid()  - given how much of an invoice is paid, says which fee types that covers.
                          Payments explicitly tagged to a fee type count first; anything else is
                          applied in fee-type priority order.
* allocate_payment()    - decides where a new payment goes: oldest balance first, or specific fee
                          types first with optional spill-over to the rest.
"""

EPS = 0.005


def _r(x):
	return round(float(x or 0) + 0.0, 2)


def split_invoice_paid(lines: list[dict], explicit: dict[str, float], paid_total: float) -> dict[str, float]:
	"""
	lines:      [{fee_type, amount, priority}] for one invoice (amount after discount)
	explicit:   fee_type -> amount allocated to it by submitted Fee Payments
	paid_total: invoice total minus outstanding (all payments and credits applied)

	Returns fee_type -> paid amount. Sum never exceeds paid_total or the line amounts.
	"""
	amounts, priority = {}, {}
	for l in lines:
		amounts[l["fee_type"]] = amounts.get(l["fee_type"], 0) + float(l["amount"] or 0)
		priority[l["fee_type"]] = min(priority.get(l["fee_type"], 999), int(l.get("priority") or 10))
	order = sorted(amounts, key=lambda ft: (priority[ft], ft))

	remaining = max(0.0, float(paid_total or 0))
	paid = {ft: 0.0 for ft in order}
	for ft in order:  # explicit allocations first
		x = min(float(explicit.get(ft, 0) or 0), amounts[ft], remaining)
		if x > 0:
			paid[ft] += x
			remaining -= x
	for ft in order:  # untagged money by priority
		x = min(amounts[ft] - paid[ft], remaining)
		if x > 0:
			paid[ft] += x
			remaining -= x
	return {ft: _r(v) for ft, v in paid.items()}


def allocate_payment(
	open_lines: list[dict],
	amount: float,
	target_fee_types: list[str] | None = None,
	spill_over: bool = True,
) -> tuple[list[dict], float]:
	"""
	open_lines: [{sales_invoice, posting_date, school_term, fee_type, priority, outstanding}]
	Returns (allocations, unallocated). Each allocation copies the line and adds allocated_amount.
	"""
	remaining = _r(amount)
	ordered = sorted(
		(l for l in open_lines if float(l.get("outstanding") or 0) > EPS),
		key=lambda l: (str(l.get("posting_date") or ""), l["sales_invoice"], int(l.get("priority") or 10), l["fee_type"]),
	)
	result: dict[tuple, dict] = {}

	def take(lines):
		nonlocal remaining
		for l in lines:
			if remaining <= EPS:
				return
			key = (l["sales_invoice"], l["fee_type"])
			already = result[key]["allocated_amount"] if key in result else 0.0
			x = _r(min(float(l["outstanding"]) - already, remaining))
			if x <= EPS:
				continue
			if key in result:
				result[key]["allocated_amount"] = _r(already + x)
			else:
				result[key] = dict(l, allocated_amount=x)
			remaining = _r(remaining - x)

	if target_fee_types:
		targets = set(target_fee_types)
		take([l for l in ordered if l["fee_type"] in targets])
		if spill_over:
			take([l for l in ordered if l["fee_type"] not in targets])
	else:
		take(ordered)

	return list(result.values()), _r(remaining)


def per_invoice_totals(allocations: list[dict]) -> dict[str, float]:
	out: dict[str, float] = {}
	for a in allocations:
		out[a["sales_invoice"]] = _r(out.get(a["sales_invoice"], 0) + a["allocated_amount"])
	return out
