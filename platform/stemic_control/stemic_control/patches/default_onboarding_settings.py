"""Stemic Settings > Onboarding starts with its defaults on existing installs too (a Single's defaults only apply when
it is first created)."""

import frappe

DEFAULTS = {"default_trial_days": 30, "default_start": "Free trial", "build_on_onboard": 1, "auto_issue_license": 1,
            "auto_renew_license": 1, "invoice_trials": 1, "trial_invoice_days": 7, "trial_reminder": 1}


def execute():
    stored = set(frappe.db.sql_list("SELECT field FROM `tabSingles` WHERE doctype = 'Stemic Settings' AND field IN %s",
                                    (tuple(DEFAULTS),)))
    for field, value in DEFAULTS.items():
        if field not in stored:
            frappe.db.set_single_value("Stemic Settings", field, value)
    frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
