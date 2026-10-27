"""Give each Stemic document type its own number sequence.

They were named with Frappe's "format:PREFIX-{#####}", whose number comes from one counter shared by every such
DocType (tabSeries key ""), so subscriptions, invoices, payments, licenses and the rest drew from the same sequence.
They are now "PREFIX-.#####" (one counter per prefix, and per year for invoices, payments and commissions). Each new
counter starts at the highest number already used with its prefix, so no new name can collide with an existing one.
Existing documents keep their names.
"""

import re

import frappe

# DocType -> how its names are built: a prefix (with the year, if any) then five digits
SERIES = {
    "SaaS Agent": r"(AGT-)(\d+)$",
    "SaaS Commission": r"(COM-\d{4}-)(\d+)$",
    "SaaS Provisioning Job": r"(JOB-)(\d+)$",
    "SaaS License": r"(LIC-)(\d+)$",
    "SaaS Invoice": r"(SINV-\d{4}-)(\d+)$",
    "SaaS Site Operation": r"(SITEOP-|SOP-)(\d+)$",
    "SaaS Payment": r"(SPAY-\d{4}-)(\d+)$",
    "SaaS Subscription": r"(SUB-)(\d+)$",
}


def execute():
    highest = {}
    for doctype, pattern in SERIES.items():
        if not frappe.db.table_exists(doctype):
            continue
        for name in frappe.get_all(doctype, pluck="name"):
            m = re.match(pattern, name)
            if m:
                prefix = "SITEOP-" if m.group(1) == "SOP-" else m.group(1)
                highest[prefix] = max(highest.get(prefix, 0), int(m.group(2)))
    for prefix, current in highest.items():
        existing = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", (prefix,))
        if not existing:
            frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)", (prefix, current))
        elif existing[0][0] < current:
            frappe.db.sql("UPDATE `tabSeries` SET current = %s WHERE name = %s", (current, prefix))
