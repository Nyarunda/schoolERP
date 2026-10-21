# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ExpenseCategory(Document):
	def validate(self):
		acc = frappe.db.get_value("Account", self.expense_account, ["root_type", "is_group"], as_dict=True)
		if acc and acc.is_group:
			frappe.throw(_("Pick a ledger account, not a group"))
		if acc and acc.root_type not in ("Expense", "Asset"):
			frappe.throw(_("{0} is not an expense account").format(self.expense_account))
