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
        self.validate_platform_domains()
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
        self.validate_backups()

    def validate_backups(self):
        if not 0 <= (self.backup_hour or 0) <= 23:
            frappe.throw("The backup hour is 0 to 23", frappe.ValidationError)
        for field in ("keep_daily", "keep_weekly", "keep_monthly", "keep_offsite_days"):
            if (self.get(field) or 0) < 0:
                frappe.throw("Backups kept cannot be negative", frappe.ValidationError)
        if self.backup_destination and self.backup_destination != "This server only":
            self.s3_endpoint_url = (self.s3_endpoint_url or "").strip().rstrip("/") or None
            if self.s3_endpoint_url and not self.s3_endpoint_url.startswith("https://"):
                frappe.throw("The storage endpoint must start with https://", frappe.ValidationError)
            self.s3_bucket = (self.s3_bucket or "").strip()
            self.s3_prefix = (self.s3_prefix or "").strip().strip("/")

    def validate_platform_domains(self):
        seen = set()
        for row in self.get("platform_domains") or []:
            row.domain = (row.domain or "").strip().lower().rstrip(".")
            if not policy.is_hostname(row.domain) or "." not in row.domain:
                frappe.throw(f"Row {row.idx}: {row.domain or 'blank'} is not a domain name", frappe.ValidationError)
            if row.domain in seen:
                frappe.throw(f"{row.domain} is listed twice", frappe.ValidationError)
            seen.add(row.domain)
        rows = self.get("platform_domains") or []
        if not rows:
            return
        defaults = [r for r in rows if r.is_default]
        if len(defaults) > 1:
            frappe.throw("Only one platform domain can be the Default", frappe.ValidationError)
        if not defaults:
            frappe.throw("Tick Default on one platform domain", frappe.ValidationError)
        if not defaults[0].enabled:
            frappe.throw(f"The Default domain ({defaults[0].domain}) must be offered for new schools", frappe.ValidationError)
        self.platform_domain = defaults[0].domain  # the single field stays in step with the Default

    def on_update(self):
        frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
        # Stemic Tax Settings (eTIMS) uses the same seller: keep it in step
        if frappe.db.exists("DocType", "Stemic Tax Settings"):
            frappe.db.set_single_value("Stemic Tax Settings", {"seller_name": self.seller_name, "seller_pin": self.seller_pin})
            frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")
