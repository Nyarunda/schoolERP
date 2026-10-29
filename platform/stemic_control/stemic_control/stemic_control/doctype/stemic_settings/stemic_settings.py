import re

import frappe
from frappe.model.document import Document

from stemic_control import policy
from stemic_control.tax_rules import valid_pin

COLOUR = re.compile(r"#[0-9a-fA-F]{6}")


class StemicSettings(Document):
    def validate(self):
        if self.platform_domain:
            self.platform_domain = self.platform_domain.strip().lower().rstrip(".")
            if not policy.is_hostname(self.platform_domain):
                frappe.throw(f"{self.platform_domain} is not a domain name", frappe.ValidationError)
        for field in ("billing_months", "payment_terms_days", "renewal_notice_days"):
            if (self.get(field) or 0) < 0:
                frappe.throw("Months and days cannot be negative", frappe.ValidationError)
        if self.billing_months == 0:
            self.billing_months = 12
        if self.seller_pin:
            self.seller_pin = self.seller_pin.strip().upper()
            if not valid_pin(self.seller_pin):
                frappe.throw(f"{self.seller_pin} is not a KRA PIN: one letter (A or P), nine digits and a letter, e.g. P051234567X",
                             frappe.ValidationError)
        if self.seller_name:
            self.seller_name = self.seller_name.strip()
        if self.post_to_accounts and self.accounting_company and "erpnext" in frappe.get_installed_apps() \
                and not frappe.db.exists("Company", self.accounting_company):
            frappe.throw(f"There is no ERPNext company called {self.accounting_company}", frappe.ValidationError)
        for field in ("brand_color", "accent_color"):
            if self.get(field) and not COLOUR.fullmatch(self.get(field)):
                frappe.throw("Colours must be written like #1b3a6b", frappe.ValidationError)
        from stemic_control.communications import check_gateway_url

        check_gateway_url(self)

    def on_update(self):
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
        # Stemic Tax Settings (eTIMS) uses the same seller: keep it in step
        if frappe.db.exists("DocType", "Stemic Tax Settings"):
            frappe.db.set_single_value("Stemic Tax Settings", {"seller_name": self.seller_name, "seller_pin": self.seller_pin})
            frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")
