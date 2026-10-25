import frappe
from frappe.model.document import Document


class SaaSSubscription(Document):
    def validate(self):
        agent = frappe.db.get_value("SaaS Tenant", self.tenant, "agent")
        if (self.agent or None) != (agent or None):
            frappe.throw("Subscription agent must match the tenant's assigned agent", frappe.ValidationError)
