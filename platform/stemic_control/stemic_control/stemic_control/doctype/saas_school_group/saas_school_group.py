import frappe
from frappe.model.document import Document


class SaaSSchoolGroup(Document):
    def validate(self):
        if self.billing_mode == "One combined bill" and not self.billing_email:
            frappe.throw("Enter the head office billing email for a combined bill", frappe.ValidationError)

    def on_update(self):
        from stemic_control import groups

        groups.sync_cost_centers(self.name)

    def on_trash(self):
        if frappe.db.exists("SaaS Tenant", {"school_group": self.name}):
            frappe.throw("Move the branches out of this group first", frappe.ValidationError)
