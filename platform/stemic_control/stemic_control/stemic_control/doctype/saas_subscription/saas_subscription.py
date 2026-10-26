import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from stemic_control import policy


class SaaSSubscription(Document):
    def validate(self):
        agent = frappe.db.get_value("SaaS Tenant", self.tenant, "agent")
        if (self.agent or None) != (agent or None):
            frappe.throw("Subscription agent must match the tenant's assigned agent", frappe.ValidationError)
        if self.ends_on and getdate(self.ends_on) < getdate(self.starts_on):
            frappe.throw("Ends On cannot be before Starts On", frappe.ValidationError)
        old = None if self.is_new() else self.get_doc_before_save()
        if old and not policy.can_move(policy.SUBSCRIPTION_TRANSITIONS, old.status, self.status):
            frappe.throw(f"A subscription cannot move from {old.status} to {self.status}", frappe.ValidationError)
