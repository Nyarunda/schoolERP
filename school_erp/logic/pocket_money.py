"""Pocket money: a learner's money held by the school, spent at the canteen/shop (no Frappe).

Every movement is a transaction; the balance is the sum of credits minus debits. Spending can never take a balance
below zero, can be capped per day, and stops while an account is frozen.
"""

CREDIT = ("Deposit", "Refund", "Adjustment In")
DEBIT = ("Purchase", "Withdrawal", "Adjustment Out")
SPENDING = ("Purchase", "Withdrawal")  # counted against the daily limit
TYPES = CREDIT + DEBIT


def signed(transaction_type: str, amount: float) -> float:
	if transaction_type in CREDIT:
		return round(float(amount), 2)
	if transaction_type in DEBIT:
		return -round(float(amount), 2)
	raise ValueError(f"Unknown transaction type {transaction_type}")


def balance_of(transactions: list[dict]) -> float:
	"""[{transaction_type, amount}] -> balance."""
	return round(sum(signed(t["transaction_type"], t["amount"]) for t in transactions), 2)


def post_problem(balance: float, transaction_type: str, amount: float, *, spent_today: float = 0, daily_limit: float = 0,
				 frozen: bool = False) -> str | None:
	"""Why this transaction can't be posted against the account, or None."""
	if transaction_type not in TYPES:
		return f"Unknown transaction type {transaction_type}"
	if not amount or float(amount) <= 0:
		return "The amount must be more than zero"
	if transaction_type in DEBIT:
		if frozen and transaction_type in SPENDING:
			return "This pocket money account is frozen"
		if round(float(balance) - float(amount), 2) < 0:
			return f"Not enough pocket money: balance is {float(balance):,.2f}"
		if transaction_type in SPENDING and daily_limit and round(float(spent_today) + float(amount), 2) > float(daily_limit):
			left = max(float(daily_limit) - float(spent_today), 0)
			return f"Over the daily limit of {float(daily_limit):,.2f} (only {left:,.2f} left today)"
	return None


def cancel_problem(balance: float, transaction_type: str, amount: float) -> str | None:
	"""Cancelling a credit takes the money back out: refused if it has already been spent."""
	if transaction_type in CREDIT and round(float(balance) - float(amount), 2) < 0:
		return f"Can't cancel: {float(amount):,.2f} was paid in but the balance is only {float(balance):,.2f}"
	return None


def crossed_low(before: float, after: float, threshold: float) -> bool:
	"""True only on the transaction that takes the balance below the threshold (one alert, not one per purchase)."""
	return bool(threshold) and before >= threshold > after


def running_balance(transactions: list[dict], opening: float = 0.0) -> list[dict]:
	"""Adds credit, debit and balance to each transaction (in the order given) for a statement."""
	bal, out = float(opening), []
	for t in transactions:
		s = signed(t["transaction_type"], t["amount"])
		bal = round(bal + s, 2)
		out.append({**t, "credit": s if s > 0 else 0.0, "debit": -s if s < 0 else 0.0, "balance": bal})
	return out
