"""Conservative per-site SMS attempt budgets for queued delivery workers.

Reservations are committed before the external provider call. Attempt counts
include failed sends, so a provider failure never releases an SMS budget slot.
"""
import frappe
from frappe.utils import nowdate


def period_limits(settings, date=None):
    day = str(date or nowdate())
    return (
        ("D:" + day, "Day", max(0, int(settings.get("sms_daily_limit") or 0))),
        ("M:" + day[:7], "Month", max(0, int(settings.get("sms_monthly_limit") or 0))),
    )


def reserve_sms(settings, recipients=1):
    """Atomic quota reservation for the queue worker. Returns False if limited.

    Use only in a dedicated background job; commits its reservation. Do not
    call within an uncommitted payment or enrollment transaction.
    """
    limits = [entry for entry in period_limits(settings) if entry[2] > 0]
    if not limits:
        return True
    if recipients < 1:
        return False
    for key, period, limit in limits:
        frappe.db.sql(
            """INSERT IGNORE INTO `tabSchool SMS Usage`
            (name, period_key, period_type, attempt_count, creation, modified,
             owner, modified_by, docstatus, idx)
            VALUES (%s,%s,%s,0,NOW(),NOW(),'Administrator','Administrator',0,0)""",
            (key, key, period),
        )
    # Always acquire locks in deterministic order to prevent deadlocks.
    for key, period, limit in sorted(limits):
        count = frappe.db.sql(
            """SELECT attempt_count FROM `tabSchool SMS Usage`
            WHERE name=%s FOR UPDATE""", key
        )[0][0]
        if count + recipients > limit:
            frappe.db.rollback()
            return False
    for key, _, _ in limits:
        frappe.db.sql(
            """UPDATE `tabSchool SMS Usage`
            SET attempt_count=attempt_count+%s, modified=NOW()
            WHERE name=%s""", (recipients, key),
        )
    frappe.db.commit()
    return True
