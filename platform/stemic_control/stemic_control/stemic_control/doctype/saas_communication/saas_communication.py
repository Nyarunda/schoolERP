import frappe
from frappe.model.document import Document


class SaaSCommunication(Document):
    def validate(self):
        if not self.flags.from_notify:
            frappe.throw("Communications are recorded when Stemic emails or texts a school", frappe.PermissionError)
