"""Which accounts each kind of school money posts to (no Frappe).

Every line is (account_key, debit, credit). Account keys are resolved to real accounts by api/ledger.py, so these
rules can be tested without a chart of accounts:

  "held"        Pocket Money Held (liability: the learners' money the school keeps)
  "shop"        Tuck Shop Sales (income)
  "adjust"      Pocket Money Adjustments (expense)
  "mode"        the cash / M-Pesa / bank account the money came in or went out through
  "suspense"    Unidentified Receipts (liability: money received, owner not known yet)
  "fines"       Library Fines (income)
  "opening"     Temporary Opening
"""

from collections import defaultdict

POCKET_MONEY = {
	# type:          (debit,   credit)
	"Deposit": ("mode", "held"),
	"Withdrawal": ("held", "mode"),
	"Purchase": ("held", "shop"),
	"Refund": ("shop", "held"),
	"Adjustment In": ("adjust", "held"),
	"Adjustment Out": ("held", "adjust"),
}
NEEDS_MODE = ("Deposit", "Withdrawal")
POSTING_MODES = ("Daily summary", "Each purchase")


def _money(amount) -> float:
	amount = round(float(amount or 0), 2)
	if amount <= 0:
		raise ValueError("The amount must be more than zero")
	return amount


def pair(debit: str, credit: str, amount) -> list[tuple[str, float, float]]:
	amount = _money(amount)
	return [(debit, amount, 0.0), (credit, 0.0, amount)]


def pocket_money_lines(transaction_type: str, amount) -> list[tuple[str, float, float]]:
	if transaction_type not in POCKET_MONEY:
		raise ValueError(f"Unknown transaction type {transaction_type}")
	debit, credit = POCKET_MONEY[transaction_type]
	return pair(debit, credit, amount)


def posts_alone(transaction_type: str, posting_mode: str) -> bool:
	"""Does this transaction get its own journal entry at once? Purchases wait for the daily summary unless the school
	posts each purchase."""
	return transaction_type != "Purchase" or posting_mode == "Each purchase"


def summarise_purchases(rows: list[dict]) -> dict[tuple, float]:
	"""Unposted purchases [{day, recorded_by, amount}] -> {(day, recorded_by): total}, one journal entry each."""
	out: dict[tuple, float] = defaultdict(float)
	for r in rows:
		out[(str(r["day"]), r.get("recorded_by") or "")] += float(r["amount"] or 0)
	return {k: round(v, 2) for k, v in out.items() if round(v, 2) > 0}


def suspense_lines(amount):
	"""An M-Pesa payment we can't match to a learner yet: in the M-Pesa account, owed to someone unknown."""
	return pair("mode", "suspense", amount)


def fine_lines(amount):
	"""A library fine paid in cash or M-Pesa (not billed to fees)."""
	return pair("mode", "fines", amount)


def opening_lines(total):
	"""Bring learners' existing pocket money into the books once: the money is somewhere (cash, bank) the bursar
	will name later, and the school owes it to the learners."""
	return pair("opening", "held", total)


def balanced(lines) -> bool:
	return round(sum(d for _, d, _ in lines), 2) == round(sum(c for _, _, c in lines), 2)


def reconciliation_gap(ledger_balance, learner_balances_total) -> float:
	"""Pocket Money Held is a liability, so its ledger balance is credit minus debit. 0 means the books agree."""
	return round(float(ledger_balance or 0) - float(learner_balances_total or 0), 2)


def can_mark_fine_paid(fine_amount, waived, invoiced, already_paid) -> str | None:
	"""Why a fine can't be marked as paid, or None."""
	if already_paid:
		return "This fine is already marked as paid"
	if invoiced:
		return "This fine was billed to the fee account: the parent pays it with the fees"
	if waived:
		return "This fine was waived"
	if round(float(fine_amount or 0), 2) <= 0:
		return "There is no fine on this loan"
	return None
