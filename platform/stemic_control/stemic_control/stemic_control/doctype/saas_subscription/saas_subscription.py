import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from stemic_control import policy


class SaaSSubscription(Document):
    def validate(self):
        from stemic_control.onboarding import EXCEPTION_FIELDS, guard_fields

        guard_fields(self, EXCEPTION_FIELDS)
        agent = frappe.db.get_value("SaaS Tenant", self.tenant, "agent")
        if (self.agent or None) != (agent or None):
            frappe.throw("Subscription agent must match the tenant's assigned agent", frappe.ValidationError)
        if self.ends_on and getdate(self.ends_on) < getdate(self.starts_on):
            frappe.throw("Ends On cannot be before Starts On", frappe.ValidationError)
        old = None if self.is_new() else self.get_doc_before_save()
        if old and not policy.can_move(policy.SUBSCRIPTION_TRANSITIONS, old.status, self.status):
            frappe.throw(f"A subscription cannot move from {old.status} to {self.status}", frappe.ValidationError)

    def on_update(self):
        link_to_school(self)


def link_to_school(sub):
    """The school's form, list and dashboards read its current subscription from SaaS Tenant.subscription: point it at
    this one when the school has none, or only a cancelled one (a newer live subscription replaces it)."""
    if sub.status == "Cancelled":
        return
    current = frappe.db.get_value("SaaS Tenant", sub.tenant, "subscription")
    if current == sub.name:
        return
    if not current or frappe.db.get_value("SaaS Subscription", current, "status") in (None, "Cancelled"):
        frappe.db.set_value("SaaS Tenant", sub.tenant, "subscription", sub.name, update_modified=False)
