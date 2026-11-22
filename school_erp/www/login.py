"""The school's sign-in page: Frappe's own sign-in (www/login.py) with the school's brand around it.

Frappe finds www pages in the last installed app first, so this file and login.html replace Frappe's. All the
sign-in logic stays Frappe's: get_context is Frappe's, and the template extends Frappe's and keeps its form and script.
Whitelisted methods (frappe.www.login.login_via_token, ...) keep their Frappe paths."""

from frappe.www import login as frappe_login

from school_erp.website import account_button, site_info

no_cache = True


def get_context(context):
	context = frappe_login.get_context(context) or context  # redirects signed-in users, as before
	try:
		info = site_info()
	except Exception:
		info = None
	if info:
		context.school_site = info
		context.school_account = account_button()
		context.school_photo = _photo()
		context.body_class = ((context.get("body_class") or "") + " ss-login-body").strip()
		context.title = f"Sign in - {info.name}"
		context.full_width = True
	return context


def _photo():
	import frappe

	try:
		return frappe.db.get_single_value("School Settings", "site_photo") or ""
	except Exception:
		return ""
