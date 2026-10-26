import json

import frappe
from frappe.model.document import Document

from stemic_control import policy


class SaaSPlan(Document):
    def validate(self):
        try:
            modules = json.loads(self.modules or "[]")
        except ValueError:
            frappe.throw("Modules must be a JSON list of module codes", frappe.ValidationError)
        if not isinstance(modules, list):
            frappe.throw("Modules must be a JSON list of module codes", frappe.ValidationError)
        unknown = [m for m in modules if m not in policy.MODULES]
        if unknown:
            frappe.throw(f"Unknown modules: {', '.join(map(str, unknown))}", frappe.ValidationError)
        # keep the catalogue order so keys and screens list modules the same way
        self.modules = json.dumps([m for m in policy.MODULES if m in modules])
        if (self.monthly_price or 0) < 0 or (self.student_limit or 0) < 0:
            frappe.throw("Price and student limit cannot be negative", frappe.ValidationError)
