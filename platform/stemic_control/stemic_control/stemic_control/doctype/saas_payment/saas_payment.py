from frappe.model.document import Document

from stemic_control import billing


class SaaSPayment(Document):
    def validate(self):
        billing.validate_payment(self)

    def before_submit(self):
        billing.validate_payment_for_submit(self)

    def on_submit(self):
        billing.apply_payment(self)

    def on_cancel(self):
        billing.reverse_payment(self)
