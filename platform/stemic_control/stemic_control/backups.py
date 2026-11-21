"""School backups from the Control Center: nightly backups, an off-server copy, retention, download and a strict
restore. Rules without Frappe are in backup_rules.py; commands run through site_runtime's operations (one at a time
per site, on record, platform admins only)."""

import os
import shutil

import frappe
from frappe.utils import cint, get_datetime, now_datetime, nowdate

from stemic_control import backup_rules as rules

LIVE = ("Active", "Suspended")  # a suspended school's data still matters
FILE_FIELDS = ("database_file", "public_file", "private_file", "config_file")
DOWNLOAD_PARTS = {"database": "database_file", "public": "public_file", "private": "private_file", "config": "config_file"}
SERVER_DOWNLOAD_LIMIT = 500 * 1048576
RESTORE_TIMEOUT = 3 * 60 * 60
SERVER_ONLY = "This server only"


def _settings():
	return frappe.get_cached_doc("Stemic Settings")


def _admin():
	from stemic_control.api import _admin as check

	check()


def _backups_dir(site):
	from stemic_control import site_runtime

	return os.path.join(site_runtime._site_dir(site), "private", "backups")


def _sites_dir():
	from stemic_control import provisioner

	return os.path.join(provisioner._bench(), "sites")


# ----------------------------------------------------------------------------- off-server storage (S3-compatible)
class Storage:
	"""An S3-compatible bucket (Backblaze B2, Wasabi, AWS S3, DigitalOcean Spaces, Cloudflare R2, MinIO)."""

	def __init__(self, settings):
		import boto3

		self.bucket = settings.s3_bucket
		self.prefix = settings.s3_prefix or ""
		self.client = boto3.client(
			"s3", endpoint_url=settings.s3_endpoint_url or None, region_name=settings.s3_region or None,
			aws_access_key_id=settings.s3_access_key,
			aws_secret_access_key=settings.get_password("s3_secret_key", raise_exception=False))

	def key(self, site, path):
		return rules.object_key(self.prefix, site, path)

	def upload(self, path, key):
		self.client.upload_file(path, self.bucket, key)

	def download(self, key, path):
		self.client.download_file(self.bucket, key, path)

	def delete(self, key):
		self.client.delete_object(Bucket=self.bucket, Key=key)

	def link(self, key, seconds=900):
		return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=seconds)


def storage(settings=None):
	settings = settings or _settings()
	if (settings.get("backup_destination") or SERVER_ONLY) == SERVER_ONLY or not settings.get("s3_bucket"):
		return None
	return Storage(settings)


def _readable(e):
	"""A storage error in words (botocore puts the provider's message in response['Error'])."""
	err = getattr(e, "response", None)
	if isinstance(err, dict) and err.get("Error"):
		return f"{err['Error'].get('Code', '')}: {err['Error'].get('Message', '')}".strip(": ")
	return str(e) or e.__class__.__name__


@frappe.whitelist(methods=["POST"])
def test_destination():
	"""Stemic Settings > Test Destination: write and delete a small file in the bucket."""
	import tempfile

	_admin()
	store = storage()
	if not store:
		return {"ok": True, "message": "Backups are kept on this server only: nothing to test."}
	key = store.key("", f".stemic-test-{frappe.generate_hash(length=8)}")
	try:
		with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
			f.write("Stemic Control Center backup destination test\n")
		store.upload(f.name, key)
		store.delete(key)
	except Exception as e:
		return {"ok": False, "message": f"Could not write to {store.bucket}: {_readable(e)}"}
	finally:
		try:
			os.unlink(f.name)
		except Exception:
			pass
	return {"ok": True, "message": f"Wrote and removed a test file in {store.bucket}/{store.prefix or ''}. Backups will be copied there."}


# ----------------------------------------------------------------------------- recording backups
def _insert(values):
	doc = frappe.get_doc({"doctype": "SaaS Backup", **values})
	doc.flags.backup_service = True
	doc.insert(ignore_permissions=True)
	return doc


def _update(name, values):
	doc = frappe.get_doc("SaaS Backup", name)
	doc.update(values)
	doc.flags.backup_service = True
	doc.save(ignore_permissions=True)
	return doc


KIND = {"Manual": "Manual", "Scheduled": "Scheduled", "Before restore": "Before restore"}


def record_backup(operation, output, kind=None):
	"""After a Backup operation succeeds: a SaaS Backup for what it wrote, then the off-server copy."""
	op = frappe.db.get_value("SaaS Site Operation", operation, ["tenant", "site", "trigger"], as_dict=True)
	found = rules.parse_backup_output(output, _sites_dir())
	if not op or not found.get("database_file"):
		return None
	store = None
	try:
		store = storage()
	except Exception:
		frappe.log_error(title="Backup storage could not be opened")
	doc = _insert({"tenant": op.tenant, "site": op.site, "taken_on": found.get("taken_on") or now_datetime(),
				   "kind": kind or KIND.get(op.trigger or "Manual", "Manual"), "size_mb": found.get("size_mb"),
				   "on_server": 1, "offsite_status": "Pending" if store else "Not set up", "operation": operation,
				   **{f: found.get(f) for f in FILE_FIELDS}})
	frappe.db.set_value("SaaS Site Operation", operation, "backup", doc.name, update_modified=False)
	frappe.db.commit()
	if store:
		upload(doc.name, store)
	return doc.name


def upload(backup, store=None):
	"""Copy a backup's files to off-server storage. A failure is recorded and alerted, and retried next night."""
	from stemic_control.alerts import notify_admins

	store = store or storage()
	doc = frappe.get_doc("SaaS Backup", backup)
	if not store or doc.offsite_status == "Uploaded":
		return doc.offsite_status
	try:
		for field in FILE_FIELDS:
			path = doc.get(field)
			if path and os.path.isfile(path):
				store.upload(path, store.key(doc.site, path))
		_update(backup, {"offsite_status": "Uploaded", "offsite_prefix": rules.object_key(store.prefix, doc.site, "")})
		status = "Uploaded"
	except Exception as e:
		_update(backup, {"offsite_status": "Failed", "note": f"Off-server copy failed: {_readable(e)}"[:500]})
		notify_admins(f"Off-server copy failed for {doc.site}", frappe.utils.escape_html(_readable(e))[:500], "SaaS Backup", backup)
		status = "Failed"
	frappe.db.commit()
	return status


def sync_server_backups(tenant):
	"""Bring the record in line with the site's backups folder: backups taken by hand appear; files deleted by hand
	are marked gone."""
	site = frappe.db.get_value("SaaS Tenant", tenant, "canonical_site")
	if not site:
		return
	folder = _backups_dir(site)
	names = os.listdir(folder) if os.path.isdir(folder) else []
	known = {r.database_file: r for r in frappe.get_all("SaaS Backup", filters={"tenant": tenant},
														 fields=["name", "database_file", "on_server", "offsite_status", "status"])}
	for stamp, parts in rules.group_server_files(names).items():
		db = os.path.join(folder, parts["database_file"])
		if db in known:
			continue
		paths = {f: os.path.join(folder, n) for f, n in parts.items()}
		size = sum(os.path.getsize(p) for p in paths.values() if os.path.isfile(p))
		_insert({"tenant": tenant, "site": site, "taken_on": rules.stamp_time(parts["database_file"]), "kind": "Found on server",
				 "size_mb": round(size / 1048576, 2), "on_server": 1,
				 "offsite_status": "Pending" if _settings().get("backup_destination") not in (None, "", SERVER_ONLY) else "Not set up",
				 **paths})
	for path, r in known.items():
		if r.on_server and r.status == "Available" and path and not os.path.isfile(path):
			gone = r.offsite_status != "Uploaded"
			_update(r.name, {"on_server": 0, **({"status": "Removed"} if gone else {})})


# ----------------------------------------------------------------------------- list, download, pin
@frappe.whitelist(methods=["GET"])
def list_backups(tenant):
	_admin()
	frappe.get_doc("SaaS Tenant", tenant).check_permission("read")
	try:
		sync_server_backups(tenant)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title=f"Could not read the backups folder of {tenant}")
	return frappe.get_all("SaaS Backup", filters={"tenant": tenant, "status": "Available"}, order_by="taken_on desc",
						  fields=["name", "taken_on", "kind", "size_mb", "on_server", "offsite_status", "pinned",
								  "public_file", "private_file"], limit_page_length=200)


@frappe.whitelist(methods=["GET"])
def download(backup, part="database"):
	"""The file from this server, or a 15-minute link to the off-server copy."""
	_admin()
	field = DOWNLOAD_PARTS.get(part)
	if not field:
		frappe.throw("Choose database, public, private or config", frappe.ValidationError)
	doc = frappe.get_doc("SaaS Backup", backup)
	path = doc.get(field)
	if not path:
		frappe.throw("This backup has no such file", frappe.ValidationError)
	if doc.on_server and os.path.isfile(path) and path.startswith(_backups_dir(doc.site) + os.sep):
		if os.path.getsize(path) > SERVER_DOWNLOAD_LIMIT:
			frappe.throw("This file is too big to download through the browser: use the off-server link, or copy it from "
						 f"the server ({path})", frappe.ValidationError)
		with open(path, "rb") as f:
			frappe.local.response.filecontent = f.read()
		frappe.local.response.filename = os.path.basename(path)
		frappe.local.response.type = "download"
		return
	store = storage()
	if doc.offsite_status == "Uploaded" and store:
		frappe.local.response.type = "redirect"
		frappe.local.response.location = store.link(store.key(doc.site, path))
		return
	frappe.throw("This file is no longer on this server or off-server", frappe.ValidationError)


@frappe.whitelist(methods=["POST"])
def toggle_pin(backup):
	_admin()
	pinned = 0 if cint(frappe.db.get_value("SaaS Backup", backup, "pinned")) else 1
	_update(backup, {"pinned": pinned})
	return {"pinned": pinned}


# ----------------------------------------------------------------------------- scheduling, retention, watchdog
def _live_tenants():
	from stemic_control import site_runtime

	out = []
	for t in frappe.get_all("SaaS Tenant", filters={"status": ("in", LIVE), "canonical_site": ("is", "set")},
							fields=["name", "canonical_site"]):
		if os.path.isdir(site_runtime._site_dir(t.canonical_site)):
			out.append(t)
	return out


def queue_backups(trigger="Scheduled"):
	"""One Backup operation per live school on this bench (skipping any with an operation already running)."""
	from stemic_control import site_runtime

	queued = []
	for t in _live_tenants():
		if site_runtime._active_operation(t.canonical_site):
			continue
		queued.append(site_runtime.queue_operation(t.name, t.canonical_site, "Backup", trigger=trigger))
	frappe.db.commit()
	return queued


@frappe.whitelist(methods=["POST"])
def backup_all_now():
	_admin()
	return {"queued": len(queue_backups("Manual"))}


def hourly():
	"""Scheduler: nightly backups at the chosen hour, then retention; the watchdog every hour."""
	s = _settings()
	now = now_datetime()
	if cint(s.get("nightly_backups")) and rules.wants_nightly(now, s.get("backup_hour"), s.get("last_nightly_run") and
															   get_datetime(s.get("last_nightly_run")).date()):
		frappe.db.set_single_value("Stemic Settings", "last_nightly_run", nowdate())
		frappe.clear_document_cache("Stemic Settings", "Stemic Settings")
		frappe.db.commit()
		try:
			queue_backups("Scheduled")
		except Exception:
			frappe.log_error(title="Nightly backups could not be queued")
		try:
			prune()
		except Exception:
			frappe.log_error(title="Backup retention failed")
		retry_uploads()
	try:
		watchdog()
	except Exception:
		frappe.log_error(title="Backup watchdog failed")


def retry_uploads():
	store = None
	try:
		store = storage()
	except Exception:
		return
	if not store:
		return
	for name in frappe.get_all("SaaS Backup", filters={"status": "Available", "on_server": 1,
													   "offsite_status": ("in", ["Pending", "Failed", "Not set up"])}, pluck="name"):
		upload(name, store)


def _remove_server_files(doc):
	folder = _backups_dir(doc.site) + os.sep
	for field in FILE_FIELDS:
		path = doc.get(field)
		if path and path.startswith(folder) and os.path.isfile(path):  # only inside that site's own backups folder
			os.unlink(path)


def prune(now=None):
	"""Retention: server copies by daily/weekly/monthly; off-server copies after N days. Pinned and newest always kept."""
	s = _settings()
	now = now or now_datetime()
	store = None
	try:
		store = storage(s)
	except Exception:
		frappe.log_error(title="Backup storage could not be opened for retention")
	removed = 0
	for tenant in frappe.get_all("SaaS Backup", filters={"status": "Available"}, pluck="tenant", distinct=True):
		rows = frappe.get_all("SaaS Backup", filters={"tenant": tenant, "status": "Available", "on_server": 1},
							  fields=["name", "taken_on", "pinned"])
		for name in rules.to_prune([{**r, "taken_on": get_datetime(r.taken_on)} for r in rows],
									s.get("keep_daily") or 0, s.get("keep_weekly") or 0, s.get("keep_monthly") or 0):
			doc = frappe.get_doc("SaaS Backup", name)
			_remove_server_files(doc)
			_update(name, {"on_server": 0, **({} if doc.offsite_status == "Uploaded" else {"status": "Removed"})})
			removed += 1
	if store:
		for r in frappe.get_all("SaaS Backup", filters={"status": "Available", "offsite_status": "Uploaded"},
								fields=["name", "taken_on", "pinned", "on_server"]):
			if rules.offsite_expired(get_datetime(r.taken_on), now, s.get("keep_offsite_days"), cint(r.pinned)):
				doc = frappe.get_doc("SaaS Backup", r.name)
				try:
					for field in FILE_FIELDS:
						if doc.get(field):
							store.delete(store.key(doc.site, doc.get(field)))
				except Exception as e:
					frappe.log_error(title=f"Off-server copy of {r.name} not removed: {_readable(e)}"[:140])
					continue
				_update(r.name, {"offsite_status": "Removed", **({} if r.on_server else {"status": "Removed"})})
				removed += 1
	frappe.db.commit()
	return removed


def watchdog(now=None):
	"""Alert when a live school has had no successful backup for 26 hours (once nightly backups have started)."""
	from stemic_control.alerts import notify_admins

	s = _settings()
	if not cint(s.get("nightly_backups")) or not s.get("last_nightly_run"):
		return []
	now = now or now_datetime()
	late = []
	for t in _live_tenants():
		last = frappe.db.get_value("SaaS Backup", {"tenant": t.name, "status": "Available"}, "max(taken_on)")
		last = get_datetime(last) if last else None
		if rules.stale(last, now):
			since = last.strftime("%Y-%m-%d %H:%M") if last else "ever"
			notify_admins(f"No backup of {t.canonical_site} since {since}",
						  "Its nightly backup did not succeed. Open the school and check Backups and Open Site.", "SaaS Tenant", t.name)
			late.append(t.name)
	return late


# ----------------------------------------------------------------------------- restore
@frappe.whitelist(methods=["POST"])
def request_restore(backup, confirm_site):
	"""Restore a school's site from one of its own backups (platform admins, typed confirmation). Runs in a worker:
	safety backup, maintenance on, restore, migrate, maintenance off, school told."""
	from stemic_control import site_runtime

	_admin()
	doc = frappe.get_doc("SaaS Backup", backup)
	frappe.db.sql("SELECT name FROM `tabSaaS Tenant` WHERE name = %s FOR UPDATE", (doc.tenant,))
	tenant = frappe.get_doc("SaaS Tenant", doc.tenant)
	tenant.check_permission("write")
	site = site_runtime._operable_site(tenant)
	if doc.status != "Available":
		frappe.throw("This backup is no longer available", frappe.ValidationError)
	if doc.site != site:
		frappe.throw(f"This backup is of {doc.site}, not of {site}: a school can only be restored from its own backups",
					 frappe.ValidationError)
	if (confirm_site or "").strip().lower() != site.lower():
		frappe.throw(f"Type the site name ({site}) exactly to confirm", frappe.ValidationError)
	if not doc.on_server and doc.offsite_status != "Uploaded":
		frappe.throw("This backup's files are no longer available", frappe.ValidationError)
	busy = site_runtime._active_operation(site)
	if busy:
		frappe.throw(f"{busy.action} ({busy.name}) is still running on {site}; wait for it to finish", frappe.ValidationError)
	op = site_runtime.queue_operation(tenant.name, site, "Restore", backup=doc.name, timeout=RESTORE_TIMEOUT,
									  method="stemic_control.backups.perform_restore")
	return {"operation": op, "status": "Queued"}


def _fetch_files(doc, store, workdir):
	"""Local paths of the backup's files, downloading off-server copies into `workdir` when not on this server."""
	paths = {}
	for field in ("database_file", "public_file", "private_file"):
		path = doc.get(field)
		if not path:
			continue
		if doc.on_server and os.path.isfile(path):
			paths[field] = path
		elif doc.offsite_status == "Uploaded" and store:
			os.makedirs(workdir, exist_ok=True)
			local = os.path.join(workdir, os.path.basename(path))
			store.download(store.key(doc.site, path), local)
			paths[field] = local
	if "database_file" not in paths:
		raise RuntimeError("The backup's database file could not be found on this server or off-server")
	return paths


def perform_restore(operation):
	"""Worker: the strict restore. Maintenance mode is always switched off again."""
	from stemic_control import config, provisioner, site_runtime
	from stemic_control.alerts import notify_admins

	rows = frappe.db.sql("SELECT site, status, tenant, backup FROM `tabSaaS Site Operation` WHERE name = %s FOR UPDATE",
						 (operation,), as_dict=True)
	if not rows or rows[0].status != "Queued":
		return rows[0].status if rows else "missing"
	site, tenant, backup = rows[0].site, rows[0].tenant, rows[0].backup
	site_runtime._set(operation, {"status": "Running", "started_on": now_datetime()})
	doc = frappe.get_doc("SaaS Backup", backup)
	root = config.secret("stemic_db_root_password")[0]
	secrets = tuple(filter(None, (site_runtime._config(site).get("db_password"), root)))
	log, maintenance_on, safety = [], False, None
	workdir = os.path.join(_backups_dir(site), f"restore-{operation}")

	def cli(*args, timeout=60 * 60):
		out = provisioner._frappe_cli("--site", site, *args, timeout=timeout, secrets_=secrets)
		log.append(f"$ frappe --site {site} {args[0]}\n{out.strip()[-3000:]}")
		return out

	def scrub(text):
		for secret in secrets:
			text = text.replace(secret, "********")
		return text

	try:
		# 1. a safety backup of the site as it is now; if this fails, nothing is touched
		out = cli("backup", "--with-files", timeout=30 * 60)
		safety_op = site_runtime.queue_operation(tenant, site, "Backup", trigger="Before restore", enqueue=False,
												 status="Succeeded", summary=f"Safety backup before restore ({operation})")
		safety = record_backup(safety_op, out, kind="Before restore")
		if safety:
			_update(safety, {"pinned": 1, "note": f"Taken before restoring {backup} ({operation})"})
		# 2. the files to restore (downloaded if only off-server)
		paths = _fetch_files(doc, storage(), workdir)
		# 3. maintenance on, restore, migrate
		cli("set-maintenance-mode", "on", timeout=5 * 60)
		maintenance_on = True
		args = ["restore", paths["database_file"]]
		if paths.get("public_file"):
			args += ["--with-public-files", paths["public_file"]]
		if paths.get("private_file"):
			args += ["--with-private-files", paths["private_file"]]
		cli(*args, *provisioner._root_args(), "--force", timeout=2 * 60 * 60)
		cli("migrate", timeout=60 * 60)
		failed = None
	except Exception as e:
		failed = scrub(str(e) if isinstance(e, provisioner.ProvisioningError) else frappe.get_traceback())
	finally:
		if maintenance_on:
			try:
				cli("set-maintenance-mode", "off", timeout=5 * 60)
			except Exception as e:
				log.append(scrub(f"Could not switch maintenance mode off: {e}"))
				notify_admins(f"{site} is still in maintenance mode after a restore",
							  f"Run: bench --site {site} set-maintenance-mode off", "SaaS Site Operation", operation)
		shutil.rmtree(workdir, ignore_errors=True)

	output = scrub("\n\n".join(log))
	when = get_datetime(doc.taken_on).strftime("%Y-%m-%d %H:%M") if doc.taken_on else doc.name
	if failed:
		site_runtime._set(operation, {"status": "Failed", "finished_on": now_datetime(), "output": (output + "\n\n" + failed)[-20000:],
									  "summary": ("Restore failed: " + failed.splitlines()[0] if failed else "Restore failed")[:500]})
		notify_admins(f"Restore of {site} failed", frappe.utils.escape_html(failed.splitlines()[0][:500]) if failed else "",
					  "SaaS Site Operation", operation)
		return "Failed"
	site_runtime._set(operation, {"status": "Succeeded", "finished_on": now_datetime(), "output": output[-20000:],
								  "summary": f"Restored to the backup of {when}; safety backup {safety or 'not recorded'}"[:500]})
	notify_admins(f"{site} restored to {when}", f"Requested by {frappe.db.get_value('SaaS Site Operation', operation, 'requested_by')}",
				  "SaaS Site Operation", operation, sms=False)
	_tell_school(tenant, site, when)
	return "Succeeded"


def _tell_school(tenant, site, when):
	t = frappe.db.get_value("SaaS Tenant", tenant, ["admin_email", "school_name"], as_dict=True)
	if not t or not t.admin_email:
		return
	try:
		frappe.sendmail(recipients=[t.admin_email], subject=f"{t.school_name}: your school system was restored",
						message=(f"<p>Your school system ({site}) was restored to how it was on <b>{when}</b>. Anything "
								 "entered after that time needs to be entered again.</p><p>Contact us if you have any questions.</p>"),
						reference_doctype="SaaS Tenant", reference_name=tenant, now=bool(frappe.flags.in_test))
	except Exception:
		frappe.log_error(title=f"Could not email {tenant} about its restore")
