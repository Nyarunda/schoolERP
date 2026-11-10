"""Framework-free tests for pocket money rules (no bench needed)."""

from school_erp.logic.pocket_money import (
	balance_of,
	cancel_problem,
	crossed_low,
	post_problem,
	running_balance,
	signed,
)


def test_signed_and_balance():
	assert signed("Deposit", 500) == 500
	assert signed("Purchase", 120.5) == -120.5
	try:
		signed("Gift", 1)
		raise AssertionError("an unknown type must be refused")
	except ValueError:
		pass
	assert balance_of([{"transaction_type": "Deposit", "amount": 1000}, {"transaction_type": "Purchase", "amount": 250},
					   {"transaction_type": "Refund", "amount": 50}, {"transaction_type": "Adjustment Out", "amount": 100}]) == 700


def test_post_problem():
	assert post_problem(0, "Deposit", 500) is None
	assert post_problem(100, "Purchase", 100) is None
	assert "Not enough" in post_problem(100, "Purchase", 100.01)
	assert "more than zero" in post_problem(100, "Deposit", 0)
	assert "frozen" in post_problem(500, "Purchase", 10, frozen=True)
	assert post_problem(500, "Adjustment Out", 10, frozen=True) is None  # the bursar can still correct a frozen account
	assert post_problem(500, "Deposit", 10, frozen=True) is None
	assert "daily limit" in post_problem(500, "Purchase", 60, spent_today=150, daily_limit=200)
	assert post_problem(500, "Purchase", 50, spent_today=150, daily_limit=200) is None
	assert post_problem(500, "Adjustment Out", 400, spent_today=150, daily_limit=200) is None  # limit is for spending only


def test_cancel_problem():
	assert cancel_problem(300, "Deposit", 300) is None
	assert "already" not in (cancel_problem(100, "Deposit", 300) or "") and cancel_problem(100, "Deposit", 300)
	assert cancel_problem(0, "Purchase", 50) is None  # cancelling a purchase gives the money back


def test_crossed_low_alerts_once():
	assert crossed_low(250, 150, 200)
	assert not crossed_low(150, 100, 200)  # already below
	assert not crossed_low(500, 300, 200)
	assert not crossed_low(500, 0, 0)


def test_running_balance():
	rows = running_balance([{"transaction_type": "Deposit", "amount": 500}, {"transaction_type": "Purchase", "amount": 80}], 20)
	assert [(r["credit"], r["debit"], r["balance"]) for r in rows] == [(500, 0, 520), (0, 80, 440)]
