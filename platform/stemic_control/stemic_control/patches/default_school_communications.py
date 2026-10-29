"""School communications (Stemic Settings > Communications) start switched on for existing installs too.

A Single's check-box defaults only apply when it is first created; on a Control Center that already had Stemic
Settings, the new switches would otherwise read as off and nothing would be sent to schools."""

import frappe

ON = ["notify_schools_by_email", "notify_welcome", "notify_invoice", "notify_payment", "notify_overdue",
      "notify_license", "notify_status", "notify_registered", "notify_admins_copy", "notify_admins_by_sms"]


def execute():
    stored = set(frappe.db.sql_list("SELECT field FROM `tabSingles` WHERE doctype = 'Stemic Settings' AND field IN %s",
                                    (tuple(ON),)))
    for field in ON:
        if field not in stored:
            frappe.db.set_single_value("Stemic Settings", field, 1)
    frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
