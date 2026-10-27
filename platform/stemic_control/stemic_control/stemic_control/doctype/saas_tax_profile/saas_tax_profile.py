import frappe
from frappe.model.document import Document

from stemic_control.tax_rules import valid_pin


class SaaSTaxProfile(Document):
    def validate(self):
        self.seller_pin = (self.seller_pin or "").strip().upper()
        # A profile can be drafted before the school's PIN arrives; it cannot be enabled without a valid one
        if (self.enabled or self.seller_pin) and not valid_pin(self.seller_pin):
            frappe.throw("Enter a valid KRA PIN (for example P051234567X) before enabling this seller profile")
        if self.enabled and not self.branch_id:
            frappe.throw("Enter the KRA branch/device mapping before enabling the profile")
        if self.integration_mode not in ("Manual", "Certified Integrator", "OSCU", "VSCU"):
            frappe.throw("Choose a supported integration mode")
        if self.default_tax_treatment not in ("Review Required", "Exempt", "Zero Rated", "Standard Rated"):
            frappe.throw("Invalid default tax treatment")
