"""License enforcement inside Frappe. Rules live in school_erp.logic.license."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from school_erp.logic import license as lic

from .public_key import PUBLIC_KEY

CACHE_KEY = "school_erp:license_state"


def get_state(refresh: bool = False) -> dict:
	if not refresh:
		cached = frappe.cache.get_value(CACHE_KEY)
		if cached:
			return cached
	# Single DocTypes live in tabSingles, so check the DocType record rather than a table
	key = frappe.db.get_single_value("School Settings", "license_key") if frappe.db.exists("DocType", "School Settings") else None
	state = lic.evaluate(key or "", PUBLIC_KEY, getdate(nowdate()), site=frappe.local.site)
	frappe.cache.set_value(CACHE_KEY, state, expires_in_sec=6 * 3600)
	return state


def clear_cache():
	frappe.cache.delete_value(CACHE_KEY)


def is_enabled(module: str) -> bool:
	return module in get_state()["modules"]


def require(module: str, doctype: str | None = None):
	msg = lic.check(get_state(), module, doctype)
	if msg:
		frappe.throw(_(msg), title=_("Not in subscription"), exc=frappe.PermissionError)


def enforce_on_doc(doc, method=None):
	"""doc_events hook: block saving/submitting documents of modules the school has not licensed."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
		return
	module = lic.DOCTYPE_MODULE.get(doc.doctype)
	if module:
		require(module, doc.doctype)


def check_student_limit():
	state = get_state()
	limit = state.get("max_students") or 0
	if limit and frappe.db.count("Student", {"status": "Active"}) >= limit:
		frappe.throw(
			_("Your subscription allows {0} active students. Contact your vendor to raise the limit.").format(limit),
			title=_("Student limit reached"),
		)


def boot_session(bootinfo):
	if frappe.session.user == "Guest":
		return
	state = get_state()
	bootinfo.school_erp = {
		"modules": state["modules"],
		"status": state["status"],
		"message": state["message"],
		"days_left": state["days_left"],
	}


def daily_license_check():
	get_state(refresh=True)
