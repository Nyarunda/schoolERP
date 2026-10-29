from frappe.model.document import Document

from stemic_control import accounting, billing, communications


class SaaSPayment(Document):
    def validate(self):
        billing.validate_payment(self)

    def before_submit(self):
        billing.validate_payment_for_submit(self)

    def on_submit(self):
        billing.apply_payment(self)
        accounting.post_payment(self)
        communications.queue("Payment Received", payment=self.name)

    def before_cancel(self):
        billing.lock_invoice(self.invoice)

    def on_cancel(self):
        billing.reverse_payment(self)
        accounting.cancel_payment(self)
