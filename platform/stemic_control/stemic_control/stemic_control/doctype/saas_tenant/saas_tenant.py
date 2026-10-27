import frappe
from frappe.model.document import Document

from stemic_control.policy import TENANT_TRANSITIONS, can_move


class SaaSTenant(Document):
    def validate(self):
        from stemic_control.onboarding import APPROVAL_FIELDS, guard_fields

        guard_fields(self, APPROVAL_FIELDS)
        before = self.get_doc_before_save()
        if before and not can_move(TENANT_TRANSITIONS, before.status, self.status):
            frappe.throw(f"A {before.status} school cannot become {self.status}", frappe.ValidationError)
