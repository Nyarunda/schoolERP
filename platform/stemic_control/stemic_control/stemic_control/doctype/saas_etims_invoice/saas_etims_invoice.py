"""Never allow an operator to mark a tax invoice as KRA-submitted without provider evidence."""
import frappe
from frappe.model.document import Document


class SaaSeTIMSInvoice(Document):
    def before_insert(self):
        if not self.flags.get("etims_service"):
            frappe.throw("Create tax records through the invoicing preparation API", frappe.PermissionError)

    def validate(self):
        old = self.get_doc_before_save()
        if old:
            frappe.throw("Tax invoice records are append-only; use controlled transitions", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Tax invoice records cannot be deleted", frappe.PermissionError)
