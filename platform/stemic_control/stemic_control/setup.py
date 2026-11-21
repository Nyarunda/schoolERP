"""Bootstrap control-plane administration without granting tenant access."""
import frappe

def install():
    if not frappe.db.exists("Role", "Stemic Platform Admin"):
        frappe.get_doc({"doctype": "Role", "role_name": "Stemic Platform Admin", "desk_access": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("Role", "Stemic Agent"):
        frappe.get_doc({"doctype": "Role", "role_name": "Stemic Agent", "desk_access": 1}).insert(ignore_permissions=True)


def after_migrate():
    fill_new_settings_defaults()


def fill_new_settings_defaults():
    """When an upgrade adds Stemic Settings fields, store their defaults once (Frappe does not, for a settings record
    that already exists). Only fields with no stored value at all are touched: the operator's choices are never
    overwritten. Without this, new backup settings read 0 (nightly off, keep 0/0/0)."""
    meta = frappe.get_meta("Stemic Settings")
    stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype = 'Stemic Settings'"))
    for df in meta.fields:
        if df.default and df.fieldname not in stored and df.fieldtype not in ("Link", "Dynamic Link"):
            frappe.db.set_single_value("Stemic Settings", df.fieldname, df.default, update_modified=False)
    frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
