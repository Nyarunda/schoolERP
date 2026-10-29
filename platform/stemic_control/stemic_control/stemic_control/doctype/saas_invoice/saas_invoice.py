import frappe
from frappe.model.document import Document

from stemic_control import accounting, billing, communications


class SaaSInvoice(Document):
    def validate(self):
        billing.compute_invoice(self)

    def before_submit(self):
        billing.validate_invoice_for_submit(self)

    def on_submit(self):
        billing.refresh_invoice(self.name)
        accounting.post_invoice(self)
        communications.queue("Invoice Issued", invoice=self.name)

    def before_cancel(self):
        billing.lock_invoice(self.name)
        from stemic_control.etims import guard_saas_invoice_cancel

        guard_saas_invoice_cancel(self.name)
        if billing.has_submitted_payment(self.name):
            frappe.throw("Cancel this invoice's payments first", frappe.ValidationError)

    def on_cancel(self):
        self.db_set("status", "Cancelled")
        accounting.cancel_invoice(self)
