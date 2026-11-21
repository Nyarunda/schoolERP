import frappe
from frappe.model.document import Document

from stemic_control.policy import TENANT_TRANSITIONS, can_move


class SaaSTenant(Document):
    def validate(self):
        from stemic_control.onboarding import APPROVAL_FIELDS, guard_fields

        guard_fields(self, APPROVAL_FIELDS)
        before = self.get_doc_before_save()
        # site_runtime.link_existing_site: an approved school given a site that already exists goes straight to Active
        linked = self.flags.link_existing_site and before and before.status in ("Approved", "Failed") and self.status == "Active"
        deleting = self.flags.via_deletion and self.status == "Deleted"  # deletion.py, after the site is gone
        if before and not linked and not deleting and not can_move(TENANT_TRANSITIONS, before.status, self.status):
            frappe.throw(f"A {before.status} school cannot become {self.status}", frappe.ValidationError)
        # suspending or resuming must also switch the school's site (api.set_tenant_status): never the status alone
        if before and "Suspended" in (before.status, self.status) and before.status != self.status \
                and not self.flags.via_status_switch:
            frappe.throw("Use Suspend or Resume on the school: they also stop or restart its site", frappe.ValidationError)
