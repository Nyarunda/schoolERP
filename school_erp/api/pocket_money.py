"""Pocket money: posting transactions against a learner's balance (row-locked), SMS to parents, the portal view."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, fmt_money, formatdate, getdate, now_datetime

from school_erp import licensing
from school_erp.logic.pocket_money import CREDIT, SPENDING, balance_of, cancel_problem, crossed_low, post_problem, signed

MONEY_ROLES = {"System Manager", "School Admin", "Bursar"}


def ensure_account(student, create=False) -> str | None:
	if frappe.db.exists("Pocket Money Account", student):
		return student
	if not create:
		return None
	frappe.get_doc({"doctype": "Pocket Money Account", "student": student}).insert(ignore_permissions=True)
	return student


def _lock(account) -> frappe._dict:
	return frappe.db.sql("""select name, balance, daily_limit, is_frozen, low_balance_alert from `tabPocket Money Account`
		where name = %s for update""", account, as_dict=True)[0]


def spent_on(student, day, exclude=None) -> float:
	start = getdate(day)
	return flt(frappe.db.sql("""select ifnull(sum(amount), 0) from `tabPocket Money Transaction`
		where student = %(s)s and docstatus = 1 and transaction_type in %(types)s and name != %(ex)s
		and posting_datetime >= %(start)s and posting_datetime < %(end)s""",
		{"s": student, "types": SPENDING, "ex": exclude or "", "start": start, "end": add_days(start, 1)})[0][0])


def check_post(doc):
	"""before_submit: lock the account row (held until the transaction ends, so two tills can't spend the same
	shilling) and refuse what the balance, daily limit or a freeze doesn't allow. Nothing is written if this fails."""
	licensing.require("pocket_money")
	account = ensure_account(doc.student, create=doc.transaction_type in CREDIT)
	if not account:
		frappe.throw(_("{0} has no pocket money yet").format(doc.student_name or doc.student))
	row = _lock(account)
	problem = post_problem(flt(row.balance), doc.transaction_type, doc.amount,
						   spent_today=spent_on(doc.student, doc.posting_datetime, exclude=doc.name),
						   daily_limit=flt(row.daily_limit), frozen=bool(cint(row.is_frozen)))
	if problem:
		frappe.throw(_(problem), title=_("Can't record this"))
	return row


def post(doc):
	"""on_submit: move the balance (the row is already locked by check_post in this transaction)."""
	row = check_post(doc)
	before = flt(row.balance)
	after = round(before + signed(doc.transaction_type, doc.amount), 2)
	frappe.db.set_value("Pocket Money Account", doc.student, {"balance": after, "last_transaction": doc.posting_datetime},
						update_modified=False)
	doc.db_set({"balance_before": before, "balance_after": after})
	from school_erp.api import ledger

	ledger.post_pocket_money(doc)  # in the same database transaction: no balance change without its posting
	if doc.transaction_type == "Deposit":
		_queue_sms(doc.name, "deposit")
	elif crossed_low(before, after, flt(row.low_balance_alert)):
		_queue_sms(doc.name, "low")


def check_unpost(doc):
	"""before_cancel: a deposit that has already been spent can't be taken back."""
	row = _lock(doc.student)
	problem = cancel_problem(flt(row.balance), doc.transaction_type, doc.amount)
	if problem:
		frappe.throw(_(problem))
	return row


def unpost(doc):
	row = check_unpost(doc)
	after = round(flt(row.balance) - signed(doc.transaction_type, doc.amount), 2)
	frappe.db.set_value("Pocket Money Account", doc.student, "balance", after, update_modified=False)
	from school_erp.api import ledger

	ledger.unpost_pocket_money(doc)


@frappe.whitelist(methods=["POST"])
def quick_transaction(student, transaction_type, amount, description=None, mode=None, reference=None):
	"""The account form's Record buttons: create and submit in one step (permissions are the user's own)."""
	licensing.require("pocket_money")
	doc = frappe.get_doc({"doctype": "Pocket Money Transaction", "student": student, "transaction_type": transaction_type,
						  "amount": flt(amount), "description": description, "mode": mode, "reference": reference,
						  "posting_datetime": now_datetime()})
	doc.insert()
	doc.submit()
	return {"name": doc.name, "balance": doc.balance_after}


@frappe.whitelist(methods=["POST"])
def recalculate(student):
	"""Bursar tool: rebuild an account's balance from its submitted transactions."""
	licensing.require("pocket_money")
	if not (MONEY_ROLES & set(frappe.get_roles())):
		raise frappe.PermissionError
	_lock(student)
	txns = frappe.get_all("Pocket Money Transaction", filters={"student": student, "docstatus": 1},
						  fields=["transaction_type", "amount"])
	balance = balance_of(txns)
	frappe.db.set_value("Pocket Money Account", student, "balance", balance, update_modified=False)
	return {"balance": balance}


# ----------------------------------------------------------------------------- SMS
TEXTS = {
	"deposit": "Dear {guardian_name}, {amount} has been added to {student_name}'s pocket money. Balance: {balance}. - {school_name}",
	"low": "Dear {guardian_name}, {student_name}'s pocket money is running low: {balance} left. - {school_name}",
}


def _queue_sms(transaction, kind):
	# not "event": frappe.enqueue has its own keyword of that name and would swallow it
	if licensing.is_enabled("messaging"):
		frappe.enqueue("school_erp.api.pocket_money.send_sms", queue="short", transaction=transaction, kind=kind,
					   enqueue_after_commit=True, now=bool(frappe.flags.in_test))


def send_sms(transaction, kind):
	from school_erp.api.messaging import sms_student

	t = frappe.db.get_value("Pocket Money Transaction", transaction, ["student", "amount", "balance_after"], as_dict=True)
	currency = frappe.db.get_single_value("School Settings", "currency")
	try:
		student = frappe.get_doc("Student", t.student)
		sms_student(student, TEXTS[kind], {"student_name": student.first_name, "amount": fmt_money(t.amount, currency=currency),
											"balance": fmt_money(t.balance_after, currency=currency),
											"school_name": frappe.db.get_single_value("School Settings", "school_name") or ""})
	except Exception:
		frappe.log_error(title=f"Pocket money SMS failed: {transaction}")


# ----------------------------------------------------------------------------- parent portal
def portal_pocket_money(student):
	if not licensing.is_enabled("pocket_money"):
		return None
	acct = frappe.db.get_value("Pocket Money Account", student, ["balance", "daily_limit", "is_frozen"], as_dict=True)
	if not acct:
		return None
	recent = frappe.get_all("Pocket Money Transaction", filters={"student": student, "docstatus": 1},
							fields=["posting_datetime", "transaction_type", "amount", "description"],
							order_by="posting_datetime desc", limit=8)
	return {"balance": flt(acct.balance), "daily_limit": flt(acct.daily_limit), "frozen": bool(acct.is_frozen),
			"recent": [{"date": formatdate(r.posting_datetime, "d MMM"), "type": r.transaction_type,
						"amount": signed(r.transaction_type, r.amount), "what": r.description or _(r.transaction_type)}
					   for r in recent]}
