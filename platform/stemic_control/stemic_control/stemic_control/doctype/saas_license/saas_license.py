import frappe
from frappe.model.document import Document


class SaaSLicense(Document):
    def validate(self):
        # Keys are only ever signed by stemic_control.licensing.issue; a hand-made record could not be verified
        if self.is_new() and not self.flags.from_issue and not frappe.flags.in_demo:
            frappe.throw("Issue licenses from the subscription (Actions > Issue License)", frappe.ValidationError)
