# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt
#
# Approval runs on the Frappe Workflow "School Expense Approval":
#   Draft -> Send for Approval -> Pending Approval -> Approve -> (Pending Final Approval -> Approve ->) Approved
#   any pending state -> Reject -> Rejected -> Resend -> Pending Approval;  Approved -> Cancel -> Cancelled
# This controller records who approved, enforces two different approvers, and sends the notifications.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from school_erp.api import expenses


class SchoolExpense(Document):
	def before_insert(self):
		self.requested_by = self.requested_by or frappe.session.user
		if not self.status:
			self.status = "Draft"

	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be more than zero"))
		if not frappe.db.get_value("Expense Category", self.expense_category, "is_active"):
			frappe.throw(_("Expense category {0} is not active").format(self.expense_category))
		self.levels_required = expenses.required_levels(self.amount)
		self.track_transition()

	def track_transition(self):
		before = self.get_doc_before_save()
		old = before.status if before else None
		if old == self.status:
			if self.status in ("Pending Approval", "Pending Final Approval") and before and flt(before.amount) != flt(self.amount):
				frappe.throw(_("The amount can't change while waiting for approval. Reject it, edit, then resend."))
			return
		user = frappe.session.user
		if self.status in ("Pending Approval",) and old in ("Draft", "Rejected", None):
			self.set("approvals", [])
			self.rejection_reason = None
		elif self.status == "Rejected":
			if not (self.rejection_reason or "").strip():
				frappe.throw(_("Write the reason in 'Rejection Reason' before rejecting"), title=_("Reason required"))
			self.append("approvals", {"level": "Final" if old == "Pending Final Approval" else "First", "user": user,
									  "action": "Rejected", "timestamp": now_datetime(), "comment": self.rejection_reason})
		elif old == "Pending Approval" and self.status in ("Pending Final Approval", "Approved"):
			if user != "Administrator" and user in (self.requested_by, self.owner):
				frappe.throw(_("You can't approve your own expense request."), frappe.PermissionError)
			self.append("approvals", {"level": "First", "user": user, "action": "Approved", "timestamp": now_datetime()})
		elif old == "Pending Final Approval" and self.status == "Approved":
			first = [a.user for a in self.approvals if a.level == "First" and a.action == "Approved"]
			if user != "Administrator" and (user in first or user in (self.requested_by, self.owner)):
				frappe.throw(_("You gave the first approval; a different person must give the final approval."), frappe.PermissionError)
			self.append("approvals", {"level": "Final", "user": user, "action": "Approved", "timestamp": now_datetime()})

	def on_update(self):
		before = self.get_doc_before_save()
		if self.docstatus == 0 and (not before or before.status != self.status):
			expenses.notify_state(self)

	def before_submit(self):
		if self.status != "Approved":
			frappe.throw(_("An expense is posted when it is approved through the workflow"))

	def on_submit(self):
		self.db_set("journal_entry", expenses.make_journal_entry(self))
		expenses.notify_state(self)

	def before_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry", "GL Entry", "Payment Ledger Entry")

	def on_cancel(self):
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.flags.ignore_permissions = True
				je.cancel()
		self.db_set("status", "Cancelled")
