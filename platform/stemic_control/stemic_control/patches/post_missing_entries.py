"""Posting is compulsory once an accounting company is set: post what is not in the books yet (older invoices, their
payments, commissions, payouts). Anything refused (a closed period) is logged; Check Ledger lists it."""

import frappe


def execute():
    from stemic_control import accounting

    if not accounting.enabled():
        return
    frappe.db.set_single_value("Stemic Settings", "post_to_accounts", 1)
    result = accounting._post_missing()
    if result["failed"]:
        frappe.log_error(title=f"{len(result['failed'])} record(s) could not be posted to the books",
                         message=frappe.as_json(result["failed"]))
