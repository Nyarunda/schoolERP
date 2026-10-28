import frappe
from frappe.model.document import Document

from stemic_control import policy


class SaaSDomain(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if before:
            if self.tenant != before.tenant or self.hostname != before.hostname:
                frappe.throw("Domain tenant and hostname cannot be reassigned", frappe.ValidationError)
            if self.status != before.status or self.verified_on != before.verified_on:
                frappe.throw("Domain verification status is managed by the verification API", frappe.PermissionError)
        elif self.status not in ("Pending Verification", "Verified"):
            frappe.throw("A new domain cannot start active", frappe.ValidationError)
        elif self.status == "Verified":
            tenant = frappe.get_doc("SaaS Tenant", self.tenant)
            from stemic_control.config import get

            base = (get("stemic_platform_domain") or "stemicschools.com").lower().rstrip(".")
            if self.domain_type != "Stemic Subdomain" or self.hostname != f"{tenant.slug}.{base}":
                frappe.throw("Custom domains require DNS verification", frappe.PermissionError)
