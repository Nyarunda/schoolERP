import frappe
from frappe.model.document import Document


class SaaSDeletion(Document):
    def validate(self):
        if not self.flags.deletion_service:
            frappe.throw("Use Delete School on the school", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Deletion records are kept as the record of what was removed", frappe.PermissionError)
