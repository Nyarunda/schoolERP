"""Give payments recorded before the unique reference key existed their key, so the database also protects them.

Payments whose reference already appears on another submitted payment are left without a key (the migration must not
fail on old data) and listed in the Error Log for someone to check.
"""

import frappe

from stemic_control.billing import reference_key


def execute():
    frappe.reload_doc("stemic_control", "doctype", "saas_payment")
    taken = set(frappe.get_all("SaaS Payment", filters={"reference_key": ("is", "set")}, pluck="reference_key"))
    conflicts = []
    for p in frappe.get_all("SaaS Payment", filters={"docstatus": 1, "reference_key": ("is", "not set")},
                            fields=["name", "mode", "reference"], order_by="creation"):
        key = reference_key(p.mode, p.reference)
        if not (p.reference or "").strip() or key in taken:
            conflicts.append(f"{p.name}: {p.mode} {p.reference or '(blank)'}")
            continue
        frappe.db.set_value("SaaS Payment", p.name, "reference_key", key, update_modified=False)
        taken.add(key)
    if conflicts:
        frappe.log_error(title="Payments left without a unique reference key",
                         message="These references are blank or already used by another submitted payment. "
                                 "Check them, then correct or cancel the duplicates:\n" + "\n".join(conflicts))
