import frappe
from frappe.model.document import Document

from stemic_control.tax_rules import valid_pin

MODES = ("Manual", "Certified Integrator", "OSCU", "VSCU")
TREATMENTS = ("Review Required", "Exempt", "Zero Rated", "Standard Rated")


class SaaSTaxProfile(Document):
    def validate(self):
        self.seller_pin = (self.seller_pin or "").strip().upper().replace(" ", "")
        self.branch_id = (self.branch_id or "").strip()
        self.integration_mode = self.integration_mode or "Manual"
        self.default_tax_treatment = self.default_tax_treatment or "Review Required"
        # A profile can be drafted before the school's PIN arrives; it cannot be enabled without a valid one
        if self.seller_pin and not valid_pin(self.seller_pin):
            frappe.throw(f"{self.seller_pin} is not a KRA PIN: it should be P or A, nine digits and a letter, for example P051234567X")
        if self.enabled and not self.seller_pin:
            frappe.throw("Enter the school's KRA PIN before marking the profile ready for tax invoices")
        if self.enabled and not self.branch_id:
            frappe.throw("Enter the KRA branch ID (usually 00) before marking the profile ready for tax invoices")
        if self.integration_mode not in MODES:
            frappe.throw("Choose a supported eTIMS connection")
        if self.default_tax_treatment not in TREATMENTS:
            frappe.throw("Choose a supported VAT treatment")
