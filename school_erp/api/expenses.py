"""Expense approvals (amount-based levels) and posting to the accounts."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, now_datetime

from school_erp import licensing
from school_erp.api.notify import notify, users_for_role
from school_erp.logic.operations import FINAL, FIRST, approval_error, levels_required, next_level, status_for


def _settings():
	return frappe.get_cached_doc("School Settings")


def role_for(level: str) -> str:
	s = _settings()
	if level == FIRST:
		return s.expense_first_approver_role or "Bursar"
	return s.expense_final_approver_role or "Head Teacher"


def required_levels(amount) -> int:
	return levels_required(flt(amount), flt(_settings().expense_single_approval_limit))


def _money(v):
	return fmt_money(v, currency=_settings().currency)


def _approvals(doc):
	return [{"level": a.level, "user": a.user, "action": a.action} for a in doc.approvals]


def _notify_approvers(doc, level):
	role = role_for(level)
	users = [u for u in users_for_role(role) if u != doc.requested_by]
	if not users:
		return
	notify(
		_("Expense to approve ({0}): {1} for {2}").format(level.lower(), _money(doc.amount), doc.payee),
		_("{0} requested {1} to {2} for: {3}").format(doc.requested_by, _money(doc.amount), doc.payee, doc.description),
		users=users, doc=doc,
		sms_text=f"Expense awaiting your {level.lower()} approval: {_money(doc.amount)} to {doc.payee} ({doc.expense_category}).",
	)


@frappe.whitelist()
def request_approval(name):
	licensing.require("expenses", "School Expense")
	doc = frappe.get_doc("School Expense", name)
	if doc.docstatus != 0 or doc.status not in ("Draft", "Rejected"):
		frappe.throw(_("This expense is already {0}").format(doc.status))
	if frappe.session.user not in (doc.owner, doc.requested_by) and not frappe.has_permission("School Expense", "submit"):
		frappe.throw(_("Only the requester can send this for approval"), frappe.PermissionError)
	doc.status = "Pending Approval"
	doc.levels_required = required_levels(doc.amount)
	doc.flags.ignore_permissions = True
	doc.save()
	_notify_approvers(doc, FIRST)
	return doc.status


@frappe.whitelist()
def decide(name, action, comment=None):
	"""action: 'Approved' or 'Rejected'."""
	licensing.require("expenses", "School Expense")
	if action not in ("Approved", "Rejected"):
		frappe.throw(_("Unknown action"))
	doc = frappe.get_doc("School Expense", name, for_update=True)
	if doc.docstatus != 0 or doc.status not in ("Pending Approval", "Pending Final Approval"):
		frappe.throw(_("This expense is not waiting for approval ({0})").format(doc.status))
	level = next_level(doc.levels_required or required_levels(doc.amount), _approvals(doc))
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	err = approval_error(user, doc.requested_by, level, roles, role_for(level), _approvals(doc),
						 is_admin="System Manager" in roles and user == "Administrator")
	if err:
		frappe.throw(_(err), frappe.PermissionError)
	if action == "Rejected" and not comment:
		frappe.throw(_("Give a reason for rejecting"))

	doc.append("approvals", {"level": level, "user": user, "action": action, "timestamp": now_datetime(), "comment": comment})
	doc.status = status_for(doc.levels_required, _approvals(doc))
	doc.flags.ignore_permissions = True
	if doc.status == "Rejected":
		doc.rejection_reason = comment
		doc.submit()  # locked, no accounting
		notify(_("Expense rejected: {0} to {1}").format(_money(doc.amount), doc.payee),
			   _("Rejected by {0}: {1}").format(user, comment), users=[doc.requested_by], doc=doc)
	elif doc.status == "Approved":
		doc.submit()  # posts the Journal Entry
		notify(_("Expense approved: {0} to {1}").format(_money(doc.amount), doc.payee),
			   _("Approved and posted ({0}).").format(doc.journal_entry), users=[doc.requested_by], doc=doc, sms=False)
	else:
		doc.save()
		_notify_approvers(doc, FINAL)
	return doc.status


def make_journal_entry(doc):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	s = _settings()
	paid_from = get_bank_cash_account(doc.mode_of_payment, s.company).get("account")
	if not paid_from:
		frappe.throw(_("Set a default account for Mode of Payment {0}").format(doc.mode_of_payment))
	cost_center = s.cost_center or frappe.db.get_value("Company", s.company, "cost_center")
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = s.company
	je.posting_date = doc.posting_date
	je.user_remark = f"{doc.name}: {doc.expense_category} - {doc.payee} - {doc.description}"[:500]
	je.cheque_no = doc.reference_no or doc.name
	je.cheque_date = doc.posting_date
	je.append("accounts", {"account": doc.expense_account, "debit_in_account_currency": flt(doc.amount), "cost_center": cost_center})
	je.append("accounts", {"account": paid_from, "credit_in_account_currency": flt(doc.amount), "cost_center": cost_center})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name
