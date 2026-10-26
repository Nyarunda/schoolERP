import frappe
from frappe.model.document import Document


class SaaSProvisioningJob(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if before:
            protected = ("tenant", "action", "idempotency_key", "status", "attempts")
            if any(self.get(key) != before.get(key) for key in protected):
                frappe.throw("Job details and status are managed by the provisioning API", frappe.PermissionError)
            return
        if self.status != "Queued" or self.action != "Create Site":
            frappe.throw("Provisioning jobs must be queued using Create Site", frappe.PermissionError)
