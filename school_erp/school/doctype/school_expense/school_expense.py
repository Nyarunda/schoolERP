# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from school_erp.api import expenses


class SchoolExpense(Document):
	def before_insert(self):
		self.requested_by = self.requested_by or frappe.session.user
		self.status = "Draft"

	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be more than zero"))
		if not frappe.db.get_value("Expense Category", self.expense_category, "is_active"):
			frappe.throw(_("Expense category {0} is not active").format(self.expense_category))
		if self.docstatus == 0 and self.status in ("Pending Approval", "Pending Final Approval") and self.has_value_changed("amount") and not self.is_new():
			# changing the amount restarts approval
			self.set("approvals", [])
			self.status = "Pending Approval"
		self.levels_required = expenses.required_levels(self.amount)

	def before_submit(self):
		if self.status not in ("Approved", "Rejected"):
			frappe.throw(_("Use 'Send for Approval'; the expense is submitted automatically once approved"))

	def on_submit(self):
		if self.status == "Approved":
			self.db_set("journal_entry", expenses.make_journal_entry(self))

	def before_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry", "GL Entry", "Payment Ledger Entry")

	def on_cancel(self):
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.flags.ignore_permissions = True
				je.cancel()
		self.db_set("status", "Cancelled")
