import frappe
from frappe.model.document import Document

from stemic_control import billing


class SaaSInvoice(Document):
    def validate(self):
        billing.compute_invoice(self)

    def on_submit(self):
        billing.refresh_invoice(self.name)

    def before_cancel(self):
        if frappe.db.exists("SaaS Payment", {"invoice": self.name, "docstatus": 1}):
            frappe.throw("Cancel this invoice's payments first", frappe.ValidationError)

    def on_cancel(self):
        self.db_set("status", "Cancelled")
