import frappe
from frappe.model.document import Document


class SaaSSiteOperation(Document):
    def validate(self):
        if not self.flags.site_operation_service:
            frappe.throw("Site operations are started from the school's Open Site dialog", frappe.PermissionError)

    def on_trash(self):
        if self.flags.deleting_school:
            return
        frappe.throw("Site operations are kept as a record of what was run", frappe.PermissionError)
