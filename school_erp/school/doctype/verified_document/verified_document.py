"""Issued verification records are append-only except controlled API lifecycle updates."""
import frappe
from frappe.model.document import Document


class VerifiedDocument(Document):
    def before_insert(self):
        if not getattr(self.flags, "verification_issuance", False):
            frappe.throw("Issue verification records through the document issuance service", frappe.PermissionError)

    def validate(self):
        original = self.get_doc_before_save()
        if original:
            frappe.throw("Issued verification records cannot be changed through Document.save", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Verification records cannot be deleted; revoke them instead", frappe.PermissionError)
