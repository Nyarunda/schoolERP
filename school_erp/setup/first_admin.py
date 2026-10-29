"""The school's own first administrator, created when Stemic builds the site.

The Control Center runs `create` on the new site (bench execute) and emails the returned link to the school's
contact: they set their own password, so no password travels by email. Running it again gives a fresh link.
"""

import frappe
from frappe.utils import validate_email_address

ROLES = ["School Admin", "System Manager"]
LINK_HOURS = 24  # Frappe's default for password links is 20 minutes: too short for a welcome email


def create(email, full_name=None):
	"""Create (or reuse) the user, give them the school admin roles, and return a one-time set-password link."""
	email = (email or "").strip().lower()
	if not validate_email_address(email):
		frappe.throw(f"{email} is not an email address")
	frappe.set_user("Administrator")
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		first, _, last = (full_name or "School Administrator").partition(" ")
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "last_name": last,
							   "user_type": "System User", "send_welcome_email": 0})
		user.insert(ignore_permissions=True)
	missing = [r for r in ROLES if r not in {row.role for row in user.roles} and frappe.db.exists("Role", r)]
	if missing:
		user.add_roles(*missing)
	if not user.enabled:
		user.enabled = 1
		user.save(ignore_permissions=True)
	seconds = LINK_HOURS * 3600
	if (frappe.get_system_settings("reset_password_link_expiry_duration") or 0) < seconds:
		frappe.db.set_single_value("System Settings", "reset_password_link_expiry_duration", seconds)
	link = user._reset_password(send_email=False)
	frappe.db.commit()
	return {"user": user.name, "link": link, "hours": LINK_HOURS}
