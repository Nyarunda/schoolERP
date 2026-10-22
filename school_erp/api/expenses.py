"""Expense approvals (amount-based levels) and posting to the accounts."""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, now_datetime

from school_erp import licensing
from school_erp.api.notify import notify, users_for_role
from school_erp.logic.operations import FINAL, FIRST, levels_required


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


def notify_state(doc):
	"""Called when an expense enters a new workflow state: tell whoever has to act, or the requester."""
	level = {"Pending Approval": FIRST, "Pending Final Approval": FINAL}.get(doc.status)
	if level:
		users = [u for u in users_for_role(role_for(level)) if u != doc.requested_by]
		notify(
			_("Expense to approve ({0}): {1} for {2}").format(level.lower(), _money(doc.amount), doc.payee),
			_("{0} requested {1} to {2} for: {3}").format(frappe.utils.get_fullname(doc.requested_by), _money(doc.amount), doc.payee, doc.description),
			users=users, doc=doc,
			sms_text=f"Expense awaiting your {level.lower()} approval: {_money(doc.amount)} to {doc.payee} ({doc.expense_category}).",
		)
	elif doc.status == "Approved":
		notify(_("Expense approved: {0} to {1}").format(_money(doc.amount), doc.payee),
			   _("Approved and posted to the accounts ({0}).").format(doc.journal_entry or ""), users=[doc.requested_by], doc=doc,
			   sms=False, indicator="green")
	elif doc.status == "Rejected":
		notify(_("Expense rejected: {0} to {1}").format(_money(doc.amount), doc.payee),
			   _("Reason: {0}. You can edit it and choose Resend.").format(doc.rejection_reason or "-"), users=[doc.requested_by], doc=doc,
			   indicator="red")


@frappe.whitelist()
def request_approval(name):
	"""Same as the workflow action 'Send for Approval' (or 'Resend' after a rejection)."""
	from frappe.model.workflow import apply_workflow

	licensing.require("expenses", "School Expense")
	doc = frappe.get_doc("School Expense", name)
	action = "Resend" if doc.status == "Rejected" else "Send for Approval"
	return apply_workflow(doc, action).status


@frappe.whitelist()
def decide(name, action, comment=None):
	"""Same as the workflow actions Approve / Reject. action: 'Approved' or 'Rejected'."""
	from frappe.model.workflow import apply_workflow

	licensing.require("expenses", "School Expense")
	if action not in ("Approved", "Rejected"):
		frappe.throw(_("Unknown action"))
	doc = frappe.get_doc("School Expense", name)
	if doc.docstatus != 0 or doc.status not in ("Pending Approval", "Pending Final Approval"):
		frappe.throw(_("This expense is not waiting for approval ({0})").format(doc.status))
	if action == "Rejected" and comment:
		doc.db_set("rejection_reason", comment)  # apply_workflow reloads the doc from the database
	return apply_workflow(doc, "Approve" if action == "Approved" else "Reject").status


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
