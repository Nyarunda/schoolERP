"""Tell the platform admins when something needs them: a failed or refused school site build, a failed site operation,
invoices that disagree with their payments.

Each alert is a notification in the bell of every platform admin (System Manager / Stemic Platform Admin), linked to
the record, which Frappe also emails (through the email queue, with a default outgoing Email Account) unless the user
switched those emails off. These happen while the workers are running; when the workers themselves stop, the
watchdog (scripts/watchdog.py) is what reports it.
"""

import frappe


def platform_admins() -> list[str]:
    return frappe.db.sql("""SELECT DISTINCT u.name FROM `tabUser` u JOIN `tabHas Role` r ON r.parent = u.name
        WHERE r.role IN ('System Manager', 'Stemic Platform Admin') AND u.enabled = 1 AND u.user_type = 'System User'
        AND u.name NOT IN ('Administrator', 'Guest')""", pluck=True)


def notify_admins(title, description="", doctype=None, name=None, sms=True):
    """Alert every platform admin once per record and title (a repeat of the same alert is not sent again): in the bell,
    by email, and by SMS when SMS to platform admins is on (Stemic Settings > Communications)."""
    from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

    users = platform_admins()
    if not users:
        return 0
    try:
        enqueue_create_notification(users, {
            "type": "Alert", "title": title[:140], "description": description, "document_type": doctype,
            "document_name": name, "from_user": "Administrator",
        }, dedupe_on=["title", "document_type", "document_name"])
    except Exception:
        frappe.log_error(title=f"Could not alert the platform admins: {title[:100]}")
        return 0
    if sms:
        try:
            from stemic_control import communications

            communications.sms_admins("Alert", f"Stemic alert: {title}"[:300], (doctype, name),
                                      key=f"alert|{title[:140]}|{doctype}|{name}")
        except Exception:
            frappe.log_error(title=f"Could not text the platform admins: {title[:100]}")
    return len(users)
