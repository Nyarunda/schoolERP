import frappe
from frappe.model.document import Document

from stemic_control.tax_rules import valid_pin


class StemicTaxSettings(Document):
    def validate(self):
        # one place to enter them: Stemic Settings > Billing (also on every invoice)
        seller = frappe.db.get_singles_dict("Stemic Settings")
        self.seller_name = seller.get("seller_name") or self.seller_name
        self.seller_pin = seller.get("seller_pin") or self.seller_pin
        if self.enabled:
            if not valid_pin(self.seller_pin):
                frappe.throw("Configure the legal Stemic seller KRA PIN before enabling invoicing")
            if not self.seller_name or not self.branch_id:
                frappe.throw("Seller legal name and KRA branch are required")
