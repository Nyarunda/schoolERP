import frappe
from frappe.model.document import Document

from stemic_control import policy


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
        from stemic_control.communications import check_gateway_url

        check_gateway_url(self)

    def on_update(self):
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
