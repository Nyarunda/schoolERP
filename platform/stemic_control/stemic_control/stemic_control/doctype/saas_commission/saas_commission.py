import frappe
from frappe.model.document import Document


class SaaSCommission(Document):
    def validate(self):
        # Commission is earned from payments (stemic_control.billing), never typed in
        if self.is_new() and not self.flags.ignore_permissions:
            frappe.throw("Commission is earned automatically when a referred school pays", frappe.PermissionError)
