"""Putting every kind of school money through the General Ledger.

Fees (Sales Invoice), fee receipts and matched M-Pesa (Payment Entry) and expenses (Journal Entry) post through
ERPNext already. This module posts the rest as Journal Entries: pocket money, M-Pesa money not matched yet
(suspense), library fines paid in cash, and checks that nothing is left out. The Dr/Cr rules are in logic/ledger.py.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate

from school_erp import licensing
from school_erp.logic import ledger as rules

MONEY_ROLES = {"System Manager", "School Admin", "Bursar", "Accounts Manager"}

# School Settings field -> (account name, root type, preferred parent group names)
ACCOUNTS = {
	"pocket_money_account": ("Pocket Money Held", "Liability", ("Current Liabilities",)),
	"tuck_shop_income_account": ("Tuck Shop Sales", "Income", ("Direct Income", "Income")),
	"pocket_money_adjustment_account": ("Pocket Money Adjustments", "Expense", ("Indirect Expenses", "Expenses")),
	"unidentified_receipts_account": ("Unidentified Receipts", "Liability", ("Current Liabilities",)),
	"library_fines_account": ("Library Fines", "Income", ("Indirect Income", "Income")),
}
KEY_FIELD = {"held": "pocket_money_account", "shop": "tuck_shop_income_account", "adjust": "pocket_money_adjustment_account",
			 "suspense": "unidentified_receipts_account", "fines": "library_fines_account"}
FUEL_CATEGORY, FUEL_ACCOUNT = "Fuel", "Fuel & Transport"


# ----------------------------------------------------------------------------- accounts
def _settings():
	return frappe.get_cached_doc("School Settings")


def _company(settings=None):
	settings = settings or _settings()
	if not settings.company:
		frappe.throw(_("Set the Company in School Settings > Accounts & IDs before money can be recorded"),
					 title=_("No company"))
	return settings.company


def _group(company, root_type, names):
	for name in names:
		found = frappe.db.get_value("Account", {"company": company, "account_name": name, "is_group": 1, "root_type": root_type})
		if found:
			return found
	return (frappe.db.get_value("Account", {"company": company, "root_type": root_type, "is_group": 1,
											"parent_account": ("is", "set")}, order_by="lft")
			or frappe.db.get_value("Account", {"company": company, "root_type": root_type, "is_group": 1}, order_by="lft"))


def _ensure_account(company, account_name, root_type, groups, account_type=None):
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name, "is_group": 0})
	if existing:
		return existing
	parent = _group(company, root_type, groups)
	if not parent:
		frappe.throw(_("No {0} group in the chart of accounts: choose the {1} account in School Settings yourself")
					 .format(root_type, account_name))
	doc = {"doctype": "Account", "account_name": account_name, "parent_account": parent, "company": company}
	if account_type:
		doc["account_type"] = account_type
	return frappe.get_doc(doc).insert(ignore_permissions=True).name


def ensure_accounts(settings, save=False):
	"""Fill in (creating where missing) the ledger accounts and the Fuel expense category. Called when School Settings
	is saved, by the migration patch, and lazily before posting."""
	if not settings.company:
		return {}
	changed = {}
	for field, (name, root, groups) in ACCOUNTS.items():
		if not settings.get(field):
			changed[field] = _ensure_account(settings.company, name, root, groups)
	if (cint(settings.get("raise_fuel_expenses")) and not settings.get("fuel_expense_category")
			and licensing.is_enabled("expenses") and licensing.is_enabled("transport")):
		if not frappe.db.exists("Expense Category", FUEL_CATEGORY):
			account = _ensure_account(settings.company, FUEL_ACCOUNT, "Expense", ("Indirect Expenses", "Expenses"))
			frappe.get_doc({"doctype": "Expense Category", "category_name": FUEL_CATEGORY, "expense_account": account,
							"is_active": 1, "description": "Fuel bought for school vehicles (raised from driver logs)"}
						   ).insert(ignore_permissions=True)
		changed["fuel_expense_category"] = FUEL_CATEGORY
	if not settings.get("pocket_money_purchase_posting"):
		changed["pocket_money_purchase_posting"] = "Daily summary"
	for field, value in changed.items():
		settings.set(field, value)
	if changed and save:
		for field, value in changed.items():
			frappe.db.set_single_value("School Settings", field, value)
		frappe.clear_document_cache("School Settings", "School Settings")
	return changed


def account(key, settings=None):
	settings = settings or _settings()
	value = settings.get(KEY_FIELD[key])
	if not value:
		ensure_accounts(settings, save=True)
		settings = _settings()
		value = settings.get(KEY_FIELD[key])
	if not value:
		frappe.throw(_("Choose the {0} account in School Settings > Accounts & IDs").format(ACCOUNTS[KEY_FIELD[key]][0]))
	return value


def mode_of_payment(mode, settings=None):
	"""Pocket money / fine mode (Cash, M-Pesa, Bank, Other) -> a Mode of Payment."""
	settings = settings or _settings()
	if mode == "M-Pesa":
		return settings.mpesa_mode_of_payment or settings.default_mode_of_payment
	if mode == "Bank":
		return settings.get("pocket_money_bank_mode") or settings.default_mode_of_payment
	return settings.default_mode_of_payment


def mode_account(mode_of_payment_name, settings=None):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	settings = settings or _settings()
	if not mode_of_payment_name:
		frappe.throw(_("Set the Default Mode of Payment in School Settings"))
	acc = (get_bank_cash_account(mode_of_payment_name, _company(settings)) or {}).get("account")
	if not acc:
		frappe.throw(_("Set a default account for Mode of Payment {0}").format(mode_of_payment_name))
	return acc


# ----------------------------------------------------------------------------- journal entries
def journal(lines, accounts: dict, posting_date, remark, reference=None) -> str:
	"""Post [(key, debit, credit)] as a submitted Journal Entry; keys are resolved through `accounts`."""
	if not rules.balanced(lines):
		frappe.throw(_("Journal lines do not balance"))
	settings = _settings()
	company = _company(settings)
	cost_center = settings.cost_center or frappe.db.get_value("Company", company, "cost_center")
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = getdate(posting_date or nowdate())
	je.user_remark = (remark or "")[:500]
	if reference:
		je.cheque_no = str(reference)[:140]
		je.cheque_date = je.posting_date
	for key, debit, credit in lines:
		je.append("accounts", {"account": accounts[key], "debit_in_account_currency": debit,
							   "credit_in_account_currency": credit, "cost_center": cost_center})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def cancel_journal(name):
	if not name:
		return
	je = frappe.get_doc("Journal Entry", name)
	if je.docstatus == 1:
		je.flags.ignore_permissions = True
		je.cancel()


def _reverse(lines):
	return [(k, c, d) for k, d, c in lines]


def _ledger_start():
	value = _settings().get("ledger_start")
	return get_datetime(value) if value else None


def in_ledger_period(posting_datetime) -> bool:
	"""Was this money recorded after pocket money started posting (older balances came in with the opening entry)?"""
	start = _ledger_start()
	return not start or get_datetime(posting_datetime) >= start


# ----------------------------------------------------------------------------- pocket money
def _pocket_accounts(transaction_type, mode, settings=None):
	settings = settings or _settings()
	accs = {key: account(key, settings) for key in ("held", "shop", "adjust")}
	if transaction_type in rules.NEEDS_MODE:
		accs["mode"] = mode_account(mode_of_payment(mode or "Cash", settings), settings)
	return accs


def post_pocket_money(doc):
	"""on_submit of a Pocket Money Transaction. Purchases in daily-summary mode wait for post_purchase_summaries."""
	settings = _settings()
	if not rules.posts_alone(doc.transaction_type, settings.get("pocket_money_purchase_posting") or "Daily summary"):
		return None
	lines = rules.pocket_money_lines(doc.transaction_type, doc.amount)
	name = journal(lines, _pocket_accounts(doc.transaction_type, doc.mode, settings), doc.posting_datetime,
				   f"Pocket money {doc.transaction_type.lower()}: {doc.student_name or doc.student} ({doc.name})",
				   doc.reference or doc.name)
	doc.db_set("journal_entry", name, update_modified=False)
	return name


def unpost_pocket_money(doc):
	"""on_cancel: reverse whatever is in the books for this transaction.
	- it has its own (or a daily summary's) entry, or it predates the ledger and is in the opening entry: post the
	  reverse, so the books follow the balance;
	- a purchase still waiting for the daily summary: nothing is in the books yet, so nothing to do."""
	if not doc.journal_entry and in_ledger_period(doc.posting_datetime):
		return None
	lines = _reverse(rules.pocket_money_lines(doc.transaction_type, doc.amount))
	name = journal(lines, _pocket_accounts(doc.transaction_type, doc.mode), nowdate(),
				   f"Cancelled pocket money {doc.transaction_type.lower()}: {doc.student_name or doc.student} ({doc.name})",
				   doc.name)
	doc.db_set("reversal_entry", name, update_modified=False)
	return name


def _unposted_purchases(before_day=None):
	filters = {"docstatus": 1, "transaction_type": "Purchase", "journal_entry": ("is", "not set")}
	rows = frappe.get_all("Pocket Money Transaction", filters=filters,
						  fields=["name", "amount", "recorded_by", "posting_datetime"], order_by="posting_datetime")
	start = _ledger_start()
	out = []
	for r in rows:
		when = get_datetime(r.posting_datetime)
		if start and when < start:
			continue  # in the opening balance already
		if before_day and getdate(when) >= getdate(before_day):
			continue
		r.day = getdate(when)
		out.append(r)
	return out


def post_purchase_summaries(up_to=None):
	"""Daily (and on demand): one Journal Entry per day per till user for purchases not yet in the books. Today's
	purchases wait until the day is over, unless `up_to` says otherwise."""
	if not licensing.is_enabled("pocket_money") or not _settings().company:
		return []
	rows = _unposted_purchases(before_day=add_days(getdate(up_to or nowdate()), 1) if up_to else nowdate())
	if not rows:
		return []
	accs = _pocket_accounts("Purchase", None)
	made = []
	for (day, user), total in rules.summarise_purchases(rows).items():
		names = [r.name for r in rows if str(r.day) == day and (r.recorded_by or "") == user]
		try:
			je = journal(rules.pocket_money_lines("Purchase", total), accs, day,
						 f"Pocket money purchases {day}, till {user or 'unknown'}: {len(names)} sale(s)", f"PM-{day}")
			frappe.db.set_value("Pocket Money Transaction", {"name": ("in", names)}, "journal_entry", je, update_modified=False)
			frappe.db.commit()
			made.append(je)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Pocket money daily posting failed for {day} / {user}")
	return made


@frappe.whitelist(methods=["POST"])
def post_purchases_now():
	"""Bursar button: post every purchase up to and including today."""
	_require_money_role()
	return {"entries": post_purchase_summaries(up_to=nowdate())}


def post_pocket_money_opening(posting_date=None):
	"""Once, when posting starts: bring existing balances into the books (Dr Temporary Opening, Cr Pocket Money Held)
	and mark the moment, so older transactions are never posted again."""
	settings = _settings()
	if settings.get("ledger_start"):
		return settings.get("pocket_money_opening_entry")
	now = now_datetime()
	total = flt(frappe.db.sql("select ifnull(sum(balance), 0) from `tabPocket Money Account`")[0][0], 2)
	name = None
	if total > 0 and settings.company:
		ensure_accounts(settings, save=True)
		opening = frappe.db.get_value("Account", {"company": settings.company, "account_type": "Temporary", "is_group": 0})
		if not opening:
			opening = _ensure_account(settings.company, "Temporary Opening", "Asset", ("Current Assets",), "Temporary")
		name = journal(rules.opening_lines(total), {"opening": opening, "held": account("held")}, posting_date or nowdate(),
					   "Pocket money held for learners when the ledger started: move Temporary Opening to the real cash/bank account",
					   "PM-OPENING")
	frappe.db.set_single_value("School Settings", "ledger_start", now)
	frappe.db.set_single_value("School Settings", "pocket_money_opening_entry", name)
	frappe.clear_document_cache("School Settings", "School Settings")
	return name


@frappe.whitelist()
def pocket_money_reconciliation():
	"""Pocket Money Held in the ledger vs the learners' balances. Purchases waiting for the daily summary are already off
	the balances but not yet in the ledger, so they are shown and allowed for."""
	from erpnext.accounts.utils import get_balance_on

	frappe.has_permission("Pocket Money Account", "read", throw=True)
	settings = _settings()
	held = settings.get("pocket_money_account")
	balances = flt(frappe.db.sql("select ifnull(sum(balance), 0) from `tabPocket Money Account`")[0][0], 2)
	pending = round(sum(flt(r.amount) for r in _unposted_purchases()), 2)
	# a liability: get_balance_on returns debit - credit, so the amount held is its negative
	ledger_balance = -flt(get_balance_on(held, company=settings.company)) if held and settings.company else 0.0
	gap = rules.reconciliation_gap(ledger_balance - pending, balances)
	return {"account": held, "ledger": round(ledger_balance, 2), "learners": balances, "awaiting_daily_posting": pending,
			"difference": gap, "agrees": abs(gap) < 0.01}


# ----------------------------------------------------------------------------- M-Pesa suspense
def post_suspense(tx) -> str | None:
	"""A real (validated) M-Pesa payment we couldn't put on a learner: into Unidentified Receipts until someone does."""
	if tx.get("suspense_entry") or flt(tx.amount) <= 0:
		return tx.get("suspense_entry")
	settings = _settings()
	accs = {"mode": mode_account(settings.mpesa_mode_of_payment or settings.default_mode_of_payment, settings),
			"suspense": account("suspense", settings)}
	name = journal(rules.suspense_lines(tx.amount), accs, getdate(tx.trans_time or nowdate()),
				   f"M-Pesa {tx.trans_id} from {tx.payer_name or tx.msisdn or 'unknown'}, account '{tx.bill_ref_number or ''}': "
				   "not matched to a learner yet", tx.trans_id)
	frappe.db.set_value("M-Pesa Transaction", tx.name, "suspense_entry", name, update_modified=False)
	return name


def clear_suspense(tx):
	"""The payment is now on a learner (Fee Payment): take it out of Unidentified Receipts."""
	if tx.get("suspense_entry"):
		cancel_journal(tx.suspense_entry)


# ----------------------------------------------------------------------------- library fines
def post_fine_paid(loan, mode, reference=None) -> str:
	settings = _settings()
	accs = {"mode": mode_account(mode_of_payment(mode, settings), settings), "fines": account("fines", settings)}
	return journal(rules.fine_lines(loan.fine_amount), accs, nowdate(),
				   f"Library fine paid ({mode}): {loan.borrower_name} - {loan.book_title} ({loan.name})", reference or loan.name)


# ----------------------------------------------------------------------------- checks
def _require_money_role():
	if not (MONEY_ROLES & set(frappe.get_roles())):
		raise frappe.PermissionError


@frappe.whitelist()
def unposted_money():
	"""Money recorded in the school system with nothing in the General Ledger. Empty means every shilling is posted."""
	_require_money_role()
	out = []
	start = _ledger_start()
	if licensing.is_enabled("pocket_money"):
		filters = {"docstatus": 1, "journal_entry": ("is", "not set"), "transaction_type": ("!=", "Purchase")}
		if start:
			filters["posting_datetime"] = (">=", start)
		for r in frappe.get_all("Pocket Money Transaction", filters=filters, fields=["name", "transaction_type", "amount"]):
			out.append({"doctype": "Pocket Money Transaction", "name": r.name, "amount": r.amount,
						"problem": f"{r.transaction_type} not posted"})
		for r in _unposted_purchases(before_day=nowdate()):
			out.append({"doctype": "Pocket Money Transaction", "name": r.name, "amount": r.amount,
						"problem": "Purchase from an earlier day not in a daily summary"})
	if licensing.is_enabled("mpesa"):
		for r in frappe.get_all("M-Pesa Transaction", filters={"status": ("in", ["Unmatched", "Failed"]),
															  "suspense_entry": ("is", "not set"), "amount": (">", 0)},
								fields=["name", "status", "amount"]):
			out.append({"doctype": "M-Pesa Transaction", "name": r.name, "amount": r.amount,
						"problem": f"{r.status} payment not in Unidentified Receipts"})
		for r in frappe.get_all("M-Pesa Transaction", filters={"status": "Posted", "fee_payment": ("is", "not set")},
								fields=["name", "amount"]):
			out.append({"doctype": "M-Pesa Transaction", "name": r.name, "amount": r.amount, "problem": "Posted without a Fee Payment"})
	if licensing.is_enabled("expenses"):
		for r in frappe.get_all("School Expense", filters={"docstatus": 1, "journal_entry": ("is", "not set")},
								fields=["name", "amount"]):
			out.append({"doctype": "School Expense", "name": r.name, "amount": r.amount, "problem": "Approved expense not posted"})
		if licensing.is_enabled("transport") and cint(_settings().get("raise_fuel_expenses")):
			filters = {"docstatus": 1, "fuel_cost": (">", 0), "fuel_expense": ("is", "not set")}
			if start:
				filters["creation"] = (">=", start)
			for r in frappe.get_all("Driver Daily Log", filters=filters, fields=["name", "fuel_cost"]):
				out.append({"doctype": "Driver Daily Log", "name": r.name, "amount": r.fuel_cost, "problem": "Fuel bought, no expense raised"})
	return out
