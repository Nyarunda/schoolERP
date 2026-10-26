import frappe
from frappe.model.document import Document


class SaaSeTIMSEvent(Document):
    def before_insert(self):
        if not getattr(self.flags, "etims_event", False):
            frappe.throw("Tax events must be created by the integration service", frappe.PermissionError)

    def validate(self):
        if self.get_doc_before_save():
            frappe.throw("Tax audit events are append-only", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Tax audit events cannot be deleted", frappe.PermissionError)
