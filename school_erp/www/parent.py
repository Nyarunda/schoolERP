import frappe
from frappe import _

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/parent"
		raise frappe.Redirect
	from school_erp.api.portal import portal_context

	try:
		data = portal_context()
	except frappe.PermissionError:
		frappe.throw(_("The parent portal is not available"), frappe.PermissionError)
	context.update(data)
	context.title = _("My Children")
	context.no_breadcrumbs = True
	context.show_sidebar = False
	return context
