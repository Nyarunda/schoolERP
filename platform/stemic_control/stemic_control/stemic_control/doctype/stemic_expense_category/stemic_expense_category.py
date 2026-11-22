import frappe
from frappe.model.document import Document


class StemicExpenseCategory(Document):
    def validate(self):
        if self.expense_account and frappe.db.get_value("Account", self.expense_account, "root_type") != "Expense":
            frappe.throw("Choose an expense account", frappe.ValidationError)
