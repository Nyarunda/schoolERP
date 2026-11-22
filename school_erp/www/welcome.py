"""The school's homepage, shown at "/" (hooks.home_page). Switched off in School Settings -> the sign-in page."""

import frappe

from school_erp.website import home_context

no_cache = 1


def get_context(context):
	data = home_context()
	if not data.site.home_on:
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect
	context.update({k: v for k, v in data.items() if k != "site"})  # school_site comes from hooks.update_website_context
	context.school_site = data.site  # hooks.update_website_context sets these again; here so the page never lacks them
	context.school_account = data.account
	context.title = data.site.name
	context.full_width = True
	context.no_breadcrumbs = True
	context.show_sidebar = False
	context.description = data.intro or data.site.motto or data.site.name
	return context
