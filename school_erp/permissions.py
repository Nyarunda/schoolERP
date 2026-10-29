"""Row-level access: ordinary staff only see their own leave, duty reports, driver logs and expense requests.
Managers (School Admin, Head Teacher, System Manager and the module's manager role) see everything.
School Viewer (read-only) sees everything too, for reading only: it never lifts the own-records rule for a change, so a
viewer who is also staff still edits only their own records."""

import frappe

MANAGERS = {"System Manager", "School Admin", "Head Teacher"}
VIEWER = "School Viewer"
READING = {None, "read", "print", "report", "export", "email"}


def has_app_permission():
	"""Only staff (desk users) see the School app; parents are website users and go to /parent."""
	if frappe.session.user == "Administrator":
		return True
	return frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"


def _roles(user):
	return set(frappe.get_roles(user))


def _staff(user):
	return frappe.db.get_value("Staff Member", {"user": user}) or ""


def _is_manager(user, extra=()):
	return bool(_roles(user) & (MANAGERS | set(extra)))


def _views_all(user, ptype=None):
	"""A School Viewer reading (never changing) any record."""
	return ptype in READING and VIEWER in _roles(user)


# ----------------------------------------------------------------------------- leave
def leave_query(user):
	user = user or frappe.session.user
	if _is_manager(user) or _views_all(user):
		return ""
	staff = frappe.db.escape(_staff(user))
	u = frappe.db.escape(user)
	return f"(`tabLeave Application`.staff_member = {staff} or `tabLeave Application`.approver = {u} or `tabLeave Application`.owner = {u})"


def leave_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_manager(user) or doc.is_new() or _views_all(user, ptype):
		return True
	return doc.staff_member == _staff(user) or doc.approver == user or doc.owner == user or doc.reliever == _staff(user)


# ----------------------------------------------------------------------------- duty reports
def duty_report_query(user):
	user = user or frappe.session.user
	if _is_manager(user) or _views_all(user):
		return ""
	return f"(`tabDuty Report`.staff_member = {frappe.db.escape(_staff(user))} or `tabDuty Report`.owner = {frappe.db.escape(user)})"


def duty_report_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_manager(user) or doc.is_new() or _views_all(user, ptype):
		return True
	return doc.staff_member == _staff(user) or doc.owner == user


# ----------------------------------------------------------------------------- driver logs
def driver_log_query(user):
	user = user or frappe.session.user
	if _is_manager(user, ("Transport Manager",)) or _views_all(user):
		return ""
	return f"(`tabDriver Daily Log`.driver = {frappe.db.escape(_staff(user))} or `tabDriver Daily Log`.owner = {frappe.db.escape(user)})"


def driver_log_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_manager(user, ("Transport Manager",)) or doc.is_new() or _views_all(user, ptype):
		return True
	return doc.driver == _staff(user) or doc.owner == user


# ----------------------------------------------------------------------------- expenses
def expense_query(user):
	user = user or frappe.session.user
	if _is_manager(user, ("Bursar",)) or _views_all(user):
		return ""
	return f"(`tabSchool Expense`.owner = {frappe.db.escape(user)} or `tabSchool Expense`.requested_by = {frappe.db.escape(user)})"


def expense_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_manager(user, ("Bursar",)) or doc.is_new() or _views_all(user, ptype):
		return True
	return doc.owner == user or doc.requested_by == user
