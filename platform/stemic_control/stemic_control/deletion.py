"""Deleting a school from the Control Center: scheduled with a 7-day grace (the school suspended meanwhile), then its
site, database, backups, domains and records are removed, keeping one final copy for 90 days and an audit record
(SaaS Deletion). Tax records (eTIMS) and invoices already with KRA are kept: they are fiscal records.
Platform admins only."""

import glob
import os
import shutil

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

GRACE_DAYS = 7
FINAL_COPY_DAYS = 90
FILED = ("Pending Submission", "Submitted")  # tax invoice statuses that are with KRA


def _admin():
	from stemic_control.api import _admin as check

	check()


def _new(values):
	doc = frappe.get_doc({"doctype": "SaaS Deletion", **values})
	doc.flags.deletion_service = True
	doc.insert(ignore_permissions=True)
	return doc


def _set(name, values):
	doc = frappe.get_doc("SaaS Deletion", name)
	doc.update(values)
	doc.flags.deletion_service = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return doc


def _open_deletion(tenant):
	return frappe.db.get_value("SaaS Deletion", {"slug": tenant, "status": ("in", ["Scheduled", "Running", "Failed"])}, "name")


def _filed_invoices(tenant):
	if not frappe.db.exists("DocType", "SaaS eTIMS Invoice"):
		return []
	return frappe.get_all("SaaS eTIMS Invoice", filters={"tenant": tenant, "status": ("in", FILED)}, pluck="saas_invoice")


# ----------------------------------------------------------------------------- preview, schedule, cancel
@frappe.whitelist(methods=["GET"])
def preview(tenant):
	"""What deleting this school removes, and what is kept."""
	from stemic_control import site_runtime

	_admin()
	t = frappe.get_doc("SaaS Tenant", tenant)
	site = t.canonical_site
	db = {}
	if site and os.path.isdir(site_runtime._site_dir(site)):
		try:
			db = site_runtime._database(site_runtime._config(site))
		except Exception:
			db = {}
	filed = _filed_invoices(tenant)
	count = lambda dt, **f: frappe.db.count(dt, {"tenant": tenant, **f}) if frappe.db.exists("DocType", dt) else 0
	return {"school": t.school_name, "slug": t.name, "site": site, "status": t.status,
			"database_mb": db.get("size_mb"), "students": db.get("students"),
			"backups": count("SaaS Backup", status="Available"), "domains": count("SaaS Domain"),
			"invoices": count("SaaS Invoice"), "payments": count("SaaS Payment"), "commissions": count("SaaS Commission"),
			"licenses": count("SaaS License"), "tax_records": count("SaaS eTIMS Invoice"), "filed_with_kra": len(filed),
			"confirm_words": f"DELETE {t.name}", "grace_days": GRACE_DAYS, "final_copy_days": FINAL_COPY_DAYS,
			"pending": _open_deletion(tenant)}


@frappe.whitelist(methods=["POST"])
def schedule(tenant, confirm, reason=None):
	"""Suspend the school now and delete it after the grace period."""
	from stemic_control import api

	_admin()
	frappe.db.sql("SELECT name FROM `tabSaaS Tenant` WHERE name = %s FOR UPDATE", (tenant,))
	t = frappe.get_doc("SaaS Tenant", tenant)
	t.check_permission("write")
	if (confirm or "").strip() != f"DELETE {t.name}":
		frappe.throw(f"Type DELETE {t.name} exactly to confirm", frappe.ValidationError)
	if t.canonical_site and t.canonical_site == frappe.local.site:
		frappe.throw("This is the Control Center's own site", frappe.ValidationError)
	if t.status == "Deleted":
		frappe.throw("This school is already deleted", frappe.ValidationError)
	if _open_deletion(tenant):
		frappe.throw("This school is already scheduled for deletion", frappe.ValidationError)
	previous = t.status
	if t.status == "Active":
		api.set_tenant_status(tenant, "Suspended", reason or "This school's account is closing")
	d = _new({"school_name": t.school_name, "slug": t.name, "site": t.canonical_site, "status": "Scheduled",
			  "scheduled_for": add_days(nowdate(), GRACE_DAYS), "requested_by": frappe.session.user,
			  "requested_on": now_datetime(), "previous_status": previous, "reason": reason})
	from stemic_control.alerts import notify_admins

	notify_admins(f"{t.school_name} will be deleted on {d.scheduled_for}",
				  f"Requested by {frappe.session.user}. Cancel Deletion on the school until then.", "SaaS Deletion", d.name, sms=False)
	return {"deletion": d.name, "scheduled_for": str(d.scheduled_for)}


@frappe.whitelist(methods=["POST"])
def cancel(tenant):
	"""Stop a scheduled deletion and put the school back as it was."""
	from stemic_control import api

	_admin()
	name = frappe.db.get_value("SaaS Deletion", {"slug": tenant, "status": ("in", ["Scheduled", "Failed"])}, "name")
	if not name:
		frappe.throw("This school is not scheduled for deletion", frappe.ValidationError)
	d = frappe.get_doc("SaaS Deletion", name)
	if d.final_backup or frappe.db.get_value("SaaS Tenant", tenant, "status") == "Deleted":
		frappe.throw("Deletion has already started: its site may be gone. Use Retry to finish it.", frappe.ValidationError)
	if d.previous_status == "Active" and frappe.db.get_value("SaaS Tenant", tenant, "status") == "Suspended":
		api.set_tenant_status(tenant, "Active")
	_set(name, {"status": "Cancelled", "error": f"Cancelled by {frappe.session.user} on {now_datetime():%Y-%m-%d %H:%M}"})
	return {"deletion": name, "status": "Cancelled"}


@frappe.whitelist(methods=["POST"])
def delete_now(deletion):
	"""Run a deletion whose grace period is over (or Retry one that failed)."""
	_admin()
	d = frappe.get_doc("SaaS Deletion", deletion)
	if d.status == "Failed":
		_set(deletion, {"status": "Scheduled", "error": None})
	elif d.status != "Scheduled":
		frappe.throw(f"This deletion is {d.status}", frappe.ValidationError)
	elif getdate(d.scheduled_for) > getdate(nowdate()):
		frappe.throw(f"The grace period runs until {d.scheduled_for}", frappe.ValidationError)
	frappe.enqueue("stemic_control.deletion.perform", queue="long", timeout=3 * 3600, deletion=deletion,
				   enqueue_after_commit=True, job_id=f"stemic-delete-{deletion}", deduplicate=True)
	return {"deletion": deletion, "status": "Queued"}


def daily():
	"""Remind the day before; delete what is due, one school after another."""
	from stemic_control.alerts import notify_admins

	tomorrow = add_days(nowdate(), 1)
	for d in frappe.get_all("SaaS Deletion", filters={"status": "Scheduled", "scheduled_for": tomorrow, "reminded": 0},
							fields=["name", "school_name", "slug"]):
		notify_admins(f"{d.school_name} will be deleted tomorrow", "Cancel Deletion on the school to keep it.", "SaaS Deletion", d.name)
		_set(d.name, {"reminded": 1})
	for name in frappe.get_all("SaaS Deletion", filters={"status": "Scheduled", "scheduled_for": ("<=", nowdate())},
							   pluck="name", order_by="scheduled_for asc"):
		perform(name)


# ----------------------------------------------------------------------------- the deletion
def _final_dir(site):
	from stemic_control import provisioner

	return os.path.join(provisioner._bench(), "stemic-final-copies", site)


def _final_copy(d, tenant, site, cli):
	"""One last backup, kept FINAL_COPY_DAYS days: off-server when set up, else outside the site folder."""
	from stemic_control import backups, site_runtime

	out = cli("backup", "--with-files", timeout=60 * 60)
	op = site_runtime.queue_operation(tenant, site, "Backup", enqueue=False, status="Succeeded",
									  summary=f"Final copy before deleting the school ({d.name})")
	name = backups.record_backup(op, out, kind="Final copy")
	if not name:
		raise RuntimeError("The final backup did not report its files")
	b = frappe.get_doc("SaaS Backup", name)
	values = {"tenant": None, "operation": None, "school_name": d.school_name, "pinned": 0,
			  "delete_after": add_days(nowdate(), FINAL_COPY_DAYS), "note": f"Final copy of {d.school_name} ({d.slug}), deletion {d.name}"}
	if b.offsite_status == "Uploaded":
		values["on_server"] = 0  # the server copy goes with the site folder
	else:  # no off-server storage (or the upload failed): keep it on the server, outside the site
		folder = _final_dir(site)
		os.makedirs(folder, exist_ok=True)
		for field in backups.FILE_FIELDS:
			path = b.get(field)
			if path and os.path.isfile(path):
				target = os.path.join(folder, os.path.basename(path))
				shutil.move(path, target)
				values[field] = target
	backups._update(name, values)
	frappe.db.commit()
	return name


def _drop(site, cli):
	from stemic_control import provisioner, site_runtime

	if os.path.isdir(site_runtime._site_dir(site)):
		cli("drop-site", site, *provisioner._root_args(), "--no-backup", "--force", site_arg=False, timeout=30 * 60)
	# Frappe moves a dropped site's folder to archived_sites/: remove that copy too (only this site's folders)
	archived = os.path.join(provisioner._bench(), "archived_sites")
	for path in glob.glob(os.path.join(archived, site)) + glob.glob(os.path.join(archived, site + "-*")):
		if os.path.isdir(path) and os.path.dirname(os.path.abspath(path)) == os.path.abspath(archived):
			shutil.rmtree(path, ignore_errors=True)


def _delete(doctype, name):
	"""Cancel (reversing its accounting through the document's own hooks) if submitted, then delete."""
	doc = frappe.get_doc(doctype, name)
	doc.flags.ignore_permissions = True
	if doc.docstatus == 1:
		doc.cancel()
		doc = frappe.get_doc(doctype, name)
	_really_delete(doc)


def _really_delete(doc):
	doc.flags.deleting_school = True
	doc.delete(ignore_permissions=True, force=True, delete_permanently=True)


def _erp_leftovers(names):
	"""Cancelled ERPNext entries of the deleted invoices and payments, then the customer, where nothing else uses them."""
	removed, kept = 0, []
	for doctype, name in names:
		if not name or not frappe.db.exists(doctype, name):
			continue
		try:
			doc = frappe.get_doc(doctype, name)
			doc.flags.ignore_permissions = True
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			removed += 1
		except Exception as e:
			frappe.db.rollback()
			kept.append(f"{doctype} {name}: {str(e)[:120]}")
	return removed, kept


def _records(tenant, final_backup):
	"""Remove the school's records; returns (removed counts, kept notes, whether the school record must stay)."""
	from stemic_control import backups

	removed, kept = {}, []
	add = lambda key, n=1: removed.__setitem__(key, removed.get(key, 0) + n)
	filed = set(_filed_invoices(tenant))
	keep_payments = set(frappe.get_all("SaaS Payment", filters={"invoice": ("in", list(filed) or [""])}, pluck="name"))
	erp = []

	# backups (off-server copies first), domains
	store = None
	try:
		store = backups.storage()
	except Exception:
		pass
	for b in frappe.get_all("SaaS Backup", filters={"tenant": tenant, "name": ("!=", final_backup or "")}, pluck="name"):
		doc = frappe.get_doc("SaaS Backup", b)
		if store and doc.offsite_status == "Uploaded":
			for field in backups.FILE_FIELDS:
				if doc.get(field):
					try:
						store.delete(store.key(doc.site, doc.get(field)))
					except Exception as e:
						kept.append(f"Off-server file of {b}: {backups._readable(e)[:120]}")
		_really_delete(doc)
		add("backups")
	for name in frappe.get_all("SaaS Domain", filters={"tenant": tenant}, pluck="name"):
		_really_delete(frappe.get_doc("SaaS Domain", name))
		add("domains")

	# money: payments, then invoices (newest first, so amendments go before what they amend)
	for name in frappe.get_all("SaaS Payment", filters={"tenant": tenant}, pluck="name", order_by="creation desc"):
		if name in keep_payments:
			kept.append(f"Payment {name} (its invoice is with KRA)")
			continue
		erp.append(("Payment Entry", frappe.db.get_value("SaaS Payment", name, "payment_entry")))
		_delete("SaaS Payment", name)
		add("payments")
	for name in frappe.get_all("SaaS Commission", filters={"tenant": tenant}, pluck="name"):
		if frappe.db.get_value("SaaS Commission", name, "invoice") in filed:
			kept.append(f"Commission {name}")
			continue
		erp.append(("Journal Entry", frappe.db.get_value("SaaS Commission", name, "journal_entry")))
		_really_delete(frappe.get_doc("SaaS Commission", name))
		add("commissions")
	for name in frappe.get_all("SaaS Invoice", filters={"tenant": tenant}, pluck="name", order_by="creation desc"):
		if name in filed:
			kept.append(f"Invoice {name} (tax invoice with KRA)")
			continue
		erp.append(("Sales Invoice", frappe.db.get_value("SaaS Invoice", name, "sales_invoice")))
		_delete("SaaS Invoice", name)
		add("invoices")

	# the rest of what belongs to the school
	frappe.db.set_value("SaaS Tenant", tenant, "subscription", None, update_modified=False)
	for doctype, key in (("SaaS License", "licenses"), ("SaaS Subscription", "subscriptions"), ("SaaS Communication", "messages"),
						 ("SaaS Provisioning Job", "provisioning jobs"), ("SaaS Site Operation", "site operations"),
						 ("SaaS Tax Profile", "tax profiles")):
		if not frappe.db.exists("DocType", doctype):
			continue
		filters = {"tenant": tenant}
		if doctype == "SaaS Subscription" and filed:
			filters["name"] = ("not in", frappe.get_all("SaaS Invoice", filters={"name": ("in", list(filed))}, pluck="subscription") or [""])
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			try:
				_delete(doctype, name)
				add(key)
			except Exception as e:
				kept.append(f"{doctype} {name}: {str(e)[:120]}")

	n, notes = _erp_leftovers(erp)
	add("accounting entries", n)
	kept += notes
	tax_records = frappe.db.count("SaaS eTIMS Invoice", {"tenant": tenant}) if frappe.db.exists("DocType", "SaaS eTIMS Invoice") else 0
	if tax_records:
		kept.append(f"{tax_records} tax record(s) (eTIMS)")
	keep_school = bool(tax_records or filed or keep_payments)
	customer = frappe.db.get_value("SaaS Tenant", tenant, "erp_customer")
	if customer and not keep_school:
		n, notes = _erp_leftovers([("Customer", customer)])
		add("accounting entries", n)
		kept += notes
	return removed, kept, keep_school


def perform(deletion):
	"""Worker: delete one scheduled school. Safe to run again after a failure (Retry)."""
	from stemic_control import config, provisioner, site_runtime
	from stemic_control.alerts import notify_admins

	rows = frappe.db.sql("SELECT status, slug, site FROM `tabSaaS Deletion` WHERE name = %s FOR UPDATE", (deletion,), as_dict=True)
	if not rows or rows[0].status != "Scheduled":
		return rows[0].status if rows else "missing"
	d = _set(deletion, {"status": "Running"})
	tenant, site = d.slug, d.site
	root = config.secret("stemic_db_root_password")[0]
	try:
		root_args = provisioner._root_args()
	except Exception:
		root_args = []
	passed = [root_args[i + 1] for i, a in enumerate(root_args[:-1]) if a == "--db-root-password"]
	secrets = tuple(filter(None, (root, *passed, site and site_runtime._config(site).get("db_password"))))

	def cli(*args, site_arg=True, timeout=60 * 60):
		full = ("--site", site, *args) if site_arg else args
		return provisioner._frappe_cli(*full, timeout=timeout, secrets_=secrets)

	def scrub(text):
		for s in secrets:
			text = (text or "").replace(s, "********")
		return text

	try:
		if not frappe.db.exists("SaaS Tenant", tenant):
			raise RuntimeError(f"School {tenant} no longer exists")
		if site and site == frappe.local.site:
			raise RuntimeError("Refusing to delete the Control Center's own site")
		busy = site and site_runtime._active_operation(site)
		if busy:
			raise RuntimeError(f"{busy.action} ({busy.name}) is still running on {site}")
		on_bench = bool(site) and os.path.isdir(site_runtime._site_dir(site))
		if on_bench and not d.final_backup:
			d = _set(deletion, {"final_backup": _final_copy(d, tenant, site, cli)})
		if site:
			_drop(site, cli)
		removed, kept, keep_school = _records(tenant, d.final_backup)
		if keep_school:
			t = frappe.get_doc("SaaS Tenant", tenant)
			t.status = "Deleted"
			t.flags.via_deletion = t.flags.via_status_switch = True
			t.save(ignore_permissions=True)
		else:
			t = frappe.get_doc("SaaS Tenant", tenant)
			t.flags.deleting_school = True
			frappe.delete_doc("SaaS Tenant", tenant, ignore_permissions=True, force=True)
			removed["school record"] = 1
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		message = scrub(str(e) if isinstance(e, (provisioner.ProvisioningError, RuntimeError)) else frappe.get_traceback())
		_set(deletion, {"status": "Failed", "error": message[-20000:]})
		notify_admins(f"Deleting {d.school_name} failed", frappe.utils.escape_html(message.splitlines()[0][:500]) if message else "",
					  "SaaS Deletion", deletion)
		return "Failed"
	_set(deletion, {"status": "Done", "done_on": now_datetime(),
					"removed": "\n".join(f"{k}: {v}" for k, v in removed.items()) + ("\nsite and database" if site else ""),
					"kept": "\n".join(kept) or None})
	notify_admins(f"{d.school_name} was deleted", f"Final copy kept until {add_days(nowdate(), FINAL_COPY_DAYS)}.",
				  "SaaS Deletion", deletion, sms=False)
	return "Done"
