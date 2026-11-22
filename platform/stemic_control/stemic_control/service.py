"""Running many schools: Update All Schools, bulk actions, automatic update after a code change, the 15-minute health
watch, certificate checks, the Service Health screen and maintenance notices. Platform admins only; every command is a
SaaS Site Operation (site_runtime), run one school at a time. Rules without Frappe: service_rules.py."""

import json
import os
import shutil
import socket
import ssl

import frappe
from frappe.utils import cint, now_datetime

from stemic_control import service_rules as rules

BULK_ACTIONS = ("Backup", "Migrate", "Clear Cache")
CACHE = "stemic_service_watch"


def _admin():
	from stemic_control.api import _admin as check

	check()


def _settings():
	return frappe.get_cached_doc("Stemic Settings")


def _live():
	from stemic_control import backups

	return backups._live_tenants()


# ----------------------------------------------------------------------------- batches
def start_batch(tenants, action, trigger="Bulk"):
	"""Record one operation per school (skipping schools with one running) and run them, in order, in one job."""
	from stemic_control import site_runtime

	if action not in BULK_ACTIONS:
		frappe.throw("Choose " + ", ".join(BULK_ACTIONS), frappe.ValidationError)
	batch = f"{action.upper().replace(' ', '-')}-{now_datetime().strftime('%Y%m%d-%H%M%S')}-{frappe.generate_hash(length=4)}"
	queued, skipped = [], []
	for t in tenants:
		busy = site_runtime._active_operation(t.canonical_site)
		if busy:
			skipped.append({"tenant": t.name, "site": t.canonical_site, "why": f"{busy.action} {busy.name} still running"})
			continue
		queued.append(site_runtime.queue_operation(t.name, t.canonical_site, action, trigger=trigger, enqueue=False, batch=batch))
	frappe.db.commit()
	if queued:
		frappe.enqueue("stemic_control.service.process_batch", queue="long", batch=batch, enqueue_after_commit=True,
					   timeout=rules.batch_timeout(len(queued), site_runtime.ACTIONS[action][1]), job_id=f"stemic-batch-{batch}",
					   deduplicate=True)
	return {"batch": batch, "queued": len(queued), "skipped": skipped}


def process_batch(batch):
	"""Worker: the batch's operations one after another (one school at a time, never two migrations at once)."""
	from stemic_control import site_runtime

	results = {}
	for op in frappe.get_all("SaaS Site Operation", filters={"batch": batch, "status": "Queued"}, pluck="name", order_by="creation asc"):
		try:
			results[op] = site_runtime.perform_operation(op)
		except Exception:
			frappe.log_error(title=f"Batch {batch}: {op} failed to run")
			results[op] = "Failed"
	failed = [op for op, status in results.items() if status != "Succeeded"]
	if failed:
		from stemic_control.alerts import notify_admins

		notify_admins(f"Batch {batch}: {len(failed)} of {len(results)} failed", ", ".join(failed)[:500], sms=False)
	return results


@frappe.whitelist(methods=["POST"])
def update_all_schools():
	_admin()
	return start_batch(_live(), "Migrate", trigger="Bulk")


@frappe.whitelist(methods=["POST"])
def bulk_action(tenants, action):
	"""The Schools list: Back Up / Update / Clear Cache for the ticked schools that live on this bench."""
	_admin()
	names = json.loads(tenants) if isinstance(tenants, str) else list(tenants or [])
	live = {t.name: t for t in _live()}
	chosen = [live[n] for n in names if n in live]
	out = start_batch(chosen, action, trigger="Bulk")
	out["not_here"] = [n for n in names if n not in live]
	return out


@frappe.whitelist(methods=["GET"])
def batch_status(batch):
	_admin()
	return frappe.get_all("SaaS Site Operation", filters={"batch": batch}, order_by="creation asc",
						  fields=["name", "tenant", "site", "action", "status", "summary", "started_on", "finished_on"])


# ----------------------------------------------------------------------------- automatic update after a code change
def code_version():
	from stemic_control import provisioner

	return rules.commit_from_git(os.path.join(provisioner._bench(), "apps", "school_erp"))


def auto_update():
	"""Hourly: the School ERP code changed since last time → update every school once."""
	s = _settings()
	version = code_version()
	if not version or version == s.get("last_code_version"):
		return None
	frappe.db.set_single_value("Stemic Settings", "last_code_version", version)
	frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
	frappe.db.commit()
	if not s.get("last_code_version") or not cint(s.get("update_after_code_change")):
		return None  # first sight of the code just records it
	return start_batch(_live(), "Migrate", trigger="After update")


# ----------------------------------------------------------------------------- health watch
def _state():
	return frappe.cache.get_value(CACHE) or {}


def _save_state(state):
	frappe.cache.set_value(CACHE, state)


def _answers(tenant):
	from stemic_control import site_runtime

	return bool(site_runtime.served_at(tenant.canonical_site, frappe.db.get_value("SaaS Tenant", tenant.name, "primary_domain")))


def watch():
	"""Every 15 minutes: is each live school answering, and is the disk filling up? Alerts on changes only."""
	from stemic_control import provisioner
	from stemic_control.alerts import notify_admins

	s = _settings()
	state = _state()
	if cint(s.get("watch_schools")):
		for t in _live():
			row = state.get(t.name, {})
			try:
				ok = _answers(t)
			except Exception:
				ok = False
			failures, change = rules.down_change(row.get("failures", 0), ok)
			state[t.name] = {**row, "failures": failures, "ok": ok, "checked": str(now_datetime())}
			if change == "down":
				notify_admins(f"{t.canonical_site} is not answering", "Two checks 15 minutes apart got no answer from "
							  "/api/method/ping. Open the school and check Open Site.", "SaaS Tenant", t.name)
			elif change == "up":
				notify_admins(f"{t.canonical_site} is answering again ({now_datetime().strftime('%Y-%m-%d %H:%M')})", "",
							  "SaaS Tenant", t.name, sms=False)
	usage = shutil.disk_usage(provisioner._bench())
	problem = rules.disk_problem(usage.total, usage.free, s.get("disk_alert_percent") or 10)
	state["_disk"] = {"total": usage.total, "free": usage.free, "problem": problem}
	if problem and not state.get("_disk_alerted"):
		notify_admins("The server is running out of disk space", problem + ". Old backups are pruned nightly; free space or "
					  "add disk before sites stop working.")
		state["_disk_alerted"] = True
	elif not problem:
		state["_disk_alerted"] = False
	_save_state(state)
	return state


def _cert_days(host, now):
	ctx = ssl.create_default_context()
	with socket.create_connection((host, 443), timeout=5) as sock:
		with ctx.wrap_socket(sock, server_hostname=host) as tls:
			return rules.cert_days_left(tls.getpeercert()["notAfter"], now)


def check_certificates():
	"""Daily: every school address's HTTPS certificate; alert when it expires soon or cannot be read."""
	from stemic_control.alerts import notify_admins

	s = _settings()
	days_limit = s.get("cert_alert_days") or 14
	now = now_datetime()
	state = _state()
	for t in _live():
		if t.canonical_site.endswith(".localhost"):
			continue
		hosts = [t.canonical_site] + frappe.get_all("SaaS Domain", filters={"tenant": t.name, "status": "Active"}, pluck="hostname")
		certs = {}
		for host in dict.fromkeys(hosts):
			try:
				days = _cert_days(host, now)
			except Exception as e:
				certs[host] = None
				notify_admins(f"No valid HTTPS certificate for {host}", str(e)[:300], "SaaS Tenant", t.name)
				continue
			certs[host] = days
			if days < days_limit:
				notify_admins(f"Certificate for {host} expires in {days} days", "Renew it (certbot renew) before schools "
							  "see a security warning.", "SaaS Tenant", t.name)
		state.setdefault(t.name, {})["certs"] = certs
	_save_state(state)
	return state


# ----------------------------------------------------------------------------- Service Health screen
@frappe.whitelist(methods=["GET"])
def service_health():
	from stemic_control import health, provisioner

	_admin()
	state = _state()
	usage = shutil.disk_usage(provisioner._bench())
	schools = []
	for t in _live():
		row = state.get(t.name, {})
		from stemic_control.backups import last_backup_time

		last_backup = last_backup_time(t.name)
		last_op = frappe.get_all("SaaS Site Operation", filters={"tenant": t.name}, fields=["action", "status", "creation"],
								 order_by="creation desc", limit=1)
		certs = [d for d in (row.get("certs") or {}).values() if d is not None]
		schools.append({"tenant": t.name, "site": t.canonical_site, "answering": row.get("ok"), "checked": row.get("checked"),
						"cert_days": min(certs) if certs else None, "last_backup": last_backup,
						"last_operation": last_op[0] if last_op else None})
	running = frappe.get_all("SaaS Site Operation", filters={"status": ("in", ["Queued", "Running"]), "batch": ("is", "set")},
							 pluck="batch", distinct=True)
	from stemic_control.backups import nightly_status

	return {"machinery": health.check(), "schools": schools, "batches_running": running, "nightly": nightly_status(),
			"disk": {"total_gb": round(usage.total / rules.GB, 1), "free_gb": round(usage.free / rules.GB, 1),
					 "problem": rules.disk_problem(usage.total, usage.free, _settings().get("disk_alert_percent") or 10)},
			"code_version": (code_version() or "")[:10]}


# ----------------------------------------------------------------------------- maintenance notice
@frappe.whitelist(methods=["POST"])
def notify_maintenance(tenants, when, message):
	"""Email each chosen school's admin about planned maintenance."""
	_admin()
	names = json.loads(tenants) if isinstance(tenants, str) else list(tenants or [])
	if not (when or "").strip() or not (message or "").strip():
		frappe.throw("Say when and what", frappe.ValidationError)
	sent = []
	for t in frappe.get_all("SaaS Tenant", filters={"name": ("in", names or [""])}, fields=["name", "school_name", "admin_email"]):
		if not t.admin_email:
			continue
		frappe.sendmail(recipients=[t.admin_email], subject=f"{t.school_name}: planned maintenance {when}",
						message=f"<p>{frappe.utils.escape_html(message)}</p><p><b>When:</b> {frappe.utils.escape_html(when)}</p>",
						reference_doctype="SaaS Tenant", reference_name=t.name, now=bool(frappe.flags.in_test))
		sent.append(t.name)
	return {"sent": sent}
