"""Watchdog for the control plane: alert when the background machinery stops (stemic_control.health).

Scheduled jobs run on the background workers, so when the workers stop nothing scheduled inside Frappe can say so.
Run this from the system's cron instead, every 5 minutes:

    */5 * * * *  cd /home/<user>/frappe-bench/sites && ../env/bin/python ../apps/stemic_control/scripts/watchdog.py admin.localhost

It emails the platform admins (System Manager / Stemic Platform Admin) straight away, without the job queue it is
reporting on, and records an Error Log. A problem is alerted when it starts and again every hour while it lasts; a
short "recovered" note follows when it clears. Without an outgoing email account it still prints the alert, so cron
mails it to the server's user. Exit status: 0 healthy, 1 something is wrong.
"""

import json
import os
import sys

SITE = sys.argv[1] if len(sys.argv) > 1 else "admin.localhost"
REPEAT_MINUTES = 60


def admins(frappe):
    users = frappe.db.sql("""SELECT DISTINCT u.name FROM `tabUser` u JOIN `tabHas Role` r ON r.parent = u.name
        WHERE r.role IN ('System Manager', 'Stemic Platform Admin') AND u.enabled = 1 AND u.user_type = 'System User'
        AND u.name NOT IN ('Administrator', 'Guest')""", pluck=True)
    return [u for u in users if frappe.utils.validate_email_address(u)]


def send(frappe, subject, lines):
    print(subject)
    for line in lines:
        print("  " + line)
    to = admins(frappe)
    if not to or not frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}):
        print("  (not emailed: no platform admin with an email address, or no default outgoing email account)")
        return
    try:
        frappe.sendmail(recipients=to, subject=subject, message="<br>".join(frappe.utils.escape_html(l) for l in lines),
                        now=True)  # straight to the mail server: the job queue may be what is down
    except Exception as e:
        print(f"  (email failed: {e})")


def main():
    import frappe
    from frappe.utils import get_datetime, now_datetime

    frappe.init(SITE, sites_path=".")
    frappe.connect()
    from stemic_control import health

    state_path = frappe.get_site_path("private", "watchdog_state.json")
    try:
        with open(state_path) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}

    problems = {p["key"]: p for p in health.check()}
    now = now_datetime()
    due = [p for key, p in problems.items()
           if key not in state or (now - get_datetime(state[key])).total_seconds() >= REPEAT_MINUTES * 60]
    recovered = [key for key in state if key not in problems]

    if due:
        lines = []
        for p in due:
            lines += [p["message"], "What to do: " + p["fix"], ""]
        send(frappe, f"Stemic Control ({SITE}): {len(problems)} problem(s) with the background jobs", lines)
        frappe.log_error(title=f"Watchdog: {len(problems)} problem(s) with the background jobs", message="\n".join(lines))
        frappe.db.commit()
        for p in due:
            state[p["key"]] = str(now)
    if recovered:
        send(frappe, f"Stemic Control ({SITE}): background jobs recovered", [f"Resolved: {key}" for key in recovered])
        for key in recovered:
            state.pop(key, None)
    if not problems and not recovered:
        print(f"{SITE}: background jobs are running")

    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
