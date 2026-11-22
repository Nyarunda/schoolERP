import frappe
from frappe.model.document import Document
from frappe.utils import flt


class StemicExpense(Document):
    def validate(self):
        if flt(self.amount) <= 0:
            frappe.throw("The amount must be more than zero", frappe.ValidationError)
        if flt(self.vat_amount) < 0 or flt(self.vat_amount) >= flt(self.amount):
            frappe.throw("VAT claimable must be less than the amount", frappe.ValidationError)
        if frappe.db.get_value("Stemic Expense Category", self.category, "enabled") == 0:
            frappe.throw(f"{self.category} is disabled", frappe.ValidationError)

    def before_submit(self):
        from stemic_control import expenses

        expenses.check_can_post()

    def on_submit(self):
        from stemic_control import expenses

        expenses.post_expense(self)

    def on_cancel(self):
        from stemic_control import expenses

        expenses.cancel_expense(self)
