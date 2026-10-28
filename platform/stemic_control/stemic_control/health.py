"""Is the machinery behind the control plane running? Background workers, the scheduler, the job queues, provisioning.

Scheduled jobs run on the background workers, so a check scheduled inside Frappe cannot report that the workers have
stopped: it would not run either. These checks are therefore run from outside as well (scripts/watchdog.py, from the
system's cron) and shown in the Control Center (operations queue, Setup Check).
"""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

SCHEDULER_SILENT = 20  # minutes without any scheduled job starting: the scheduler process is not running
QUEUE_WAIT = 10  # minutes a background job may wait before it counts as stuck
PROVISION_WAIT = 15  # minutes a site job may stay Queued


def _problem(key, message, fix):
    return {"key": key, "message": message, "fix": fix}


def _workers():
    """How many workers are running and the oldest job waiting in their queues (minutes), or an error message."""
    from datetime import datetime, timezone

    from frappe.utils.background_jobs import get_queue, get_workers

    workers = len(get_workers())
    oldest = 0
    now = datetime.now(timezone.utc)  # the queue records times in UTC, not the site's time zone
    for name in ("short", "default", "long"):
        queue = get_queue(name)
        for job_id in queue.job_ids[:20]:
            job = queue.fetch_job(job_id)
            if job and job.enqueued_at:
                enqueued = job.enqueued_at if job.enqueued_at.tzinfo else job.enqueued_at.replace(tzinfo=timezone.utc)
                oldest = max(oldest, (now - enqueued).total_seconds() / 60)
    return workers, oldest


def check():
    """Everything wrong with the background machinery right now; an empty list means it is running."""
    from frappe.utils.scheduler import is_scheduler_disabled

    from stemic_control import provisioner

    out = []
    try:
        workers, oldest = _workers()
    except Exception as e:
        out.append(_problem("redis", f"The job queue (Redis) cannot be reached: {str(e)[:120]}",
                            "Start Redis: bench start (development) or check the redis_queue service (production)."))
        workers, oldest = None, 0
    if workers == 0:
        out.append(_problem("workers", "No background worker is running: no site is built, no backup taken, no daily "
                                       "billing or reminders run.",
                            "Start them: bench start (development); in production the process manager (supervisor or "
                            "systemd, from bench setup production) restarts them."))
    elif workers and oldest > QUEUE_WAIT:
        out.append(_problem("backlog", f"Background jobs have waited {oldest:.0f} minutes for a worker.",
                            "The workers are busy or stuck: check their logs (logs/worker.error.log) and restart them."))
    if is_scheduler_disabled(verbose=False):
        out.append(_problem("scheduler_off", "The scheduler is switched off: daily billing, the provisioning queue and "
                                             "renewal invoices do not run.",
                            "bench --site <admin site> enable-scheduler"))
    else:
        last = frappe.db.sql("SELECT MAX(last_execution) FROM `tabScheduled Job Type` WHERE stopped = 0")[0][0]
        if last and get_datetime(last) < add_to_date(now_datetime(), minutes=-SCHEDULER_SILENT):
            silent = (now_datetime() - get_datetime(last)).total_seconds() / 60
            out.append(_problem("scheduler_stopped", f"No scheduled job has started for {silent:.0f} minutes: the "
                                                     "scheduler process is not running.",
                                "Start it: bench start (development); in production the process manager runs bench "
                                "schedule."))
    if provisioner.enabled():
        cutoff = add_to_date(now_datetime(), minutes=-PROVISION_WAIT)
        demo = frappe.get_all("SaaS Tenant", filters={"notes": provisioner.DEMO_NOTE}, pluck="name") or [""]
        waiting = frappe.db.count("SaaS Provisioning Job", {"status": "Queued", "creation": ("<", cutoff),
                                                            "tenant": ("not in", demo)})  # demo schools are never built
        if waiting:
            out.append(_problem("provisioning", f"{waiting} school site job(s) have waited over {PROVISION_WAIT} "
                                                "minutes to be built.",
                                "Open the school and use Actions > Provision Now; the dialog says why it is waiting."))
    return out
