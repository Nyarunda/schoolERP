"""Bootstrap control-plane administration without granting tenant access."""
import frappe

def install():
    if not frappe.db.exists("Role", "Stemic Platform Admin"):
        frappe.get_doc({"doctype": "Role", "role_name": "Stemic Platform Admin", "desk_access": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("Role", "Stemic Agent"):
        frappe.get_doc({"doctype": "Role", "role_name": "Stemic Agent", "desk_access": 1}).insert(ignore_permissions=True)
