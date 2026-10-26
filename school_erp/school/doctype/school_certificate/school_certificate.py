import frappe
from frappe.model.document import Document


class SchoolCertificate(Document):
    def validate(self):
        old = self.get_doc_before_save()
        if old and old.status != "Draft":
            protected = ("student", "certificate_type", "recipient", "body", "purpose", "issue_date")
            if any(self.get(key) != old.get(key) for key in protected):
                frappe.throw("Approved certificates cannot be edited. Revoke and issue a new one.", frappe.PermissionError)
        if old and self.status != old.status:
            frappe.throw("Use the approval/revocation action for status changes", frappe.PermissionError)
        if not old and self.status != "Draft":
            frappe.throw("New certificates must start in Draft", frappe.PermissionError)
