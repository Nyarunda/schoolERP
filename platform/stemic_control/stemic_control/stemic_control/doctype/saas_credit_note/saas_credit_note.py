import frappe
from frappe.model.document import Document


class SaaSCreditNote(Document):
    def validate(self):
        from stemic_control import credit_notes

        credit_notes.validate(self)

    def before_submit(self):
        from stemic_control import credit_notes

        credit_notes.validate(self, submitting=True)

    def on_submit(self):
        from stemic_control import credit_notes

        credit_notes.on_submit(self)

    def on_update_after_submit(self):
        if self.kra_credit_reference and self.tax_credit_status == "Needed":
            self.db_set("tax_credit_status", "Done")

    def before_cancel(self):
        from stemic_control import billing

        billing.lock_invoice(self.invoice)

    def on_cancel(self):
        from stemic_control import credit_notes

        credit_notes.on_cancel(self)
