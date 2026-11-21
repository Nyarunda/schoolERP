import frappe
from frappe.model.document import Document


class SaaSBackup(Document):
    def validate(self):
        if not self.flags.backup_service:
            frappe.throw("Backups are recorded by the Control Center when they are taken", frappe.PermissionError)

    def on_trash(self):
        if not self.flags.deleting_school:
            frappe.throw("Backups are removed by the retention rules (or unpinned and left to them), not deleted by hand",
                         frappe.PermissionError)
