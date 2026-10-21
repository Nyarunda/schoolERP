# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, nowdate, strip_html


class SchoolNotice(Document):
	def before_insert(self):
		self.posted_by = frappe.session.user

	def validate(self):
		if not self.expiry_date:
			self.expiry_date = add_days(self.publish_date, 14)
		if getdate(self.expiry_date) < getdate(self.publish_date):
			frappe.throw(_("'Show Until' is before the publish date"))

	def after_insert(self):
		if getdate(self.publish_date) <= getdate(nowdate()):
			publish(self)


def audience_staff(audience: str) -> list[dict]:
	filters = {"status": ("!=", "Left")}
	if audience == "Teaching Staff":
		filters["staff_type"] = "Teaching"
	elif audience == "Non-Teaching Staff":
		filters["staff_type"] = ("!=", "Teaching")
	elif audience == "Drivers":
		filters["staff_type"] = "Driver"
	rows = frappe.get_all("Staff Member", filters=filters, fields=["name", "user", "phone"])
	if audience == "Management":
		managers = set()
		for role in ("Head Teacher", "School Admin", "Bursar"):
			from school_erp.api.notify import users_for_role

			managers |= set(users_for_role(role))
		rows = [r for r in rows if r.user in managers]
	return rows


def notice_users(notice) -> set[str]:
	users = {r.user for r in audience_staff(notice.audience) if r.user}
	if notice.audience == "Management":
		from school_erp.api.notify import users_for_role

		for role in ("Head Teacher", "School Admin"):
			users |= set(users_for_role(role))
	return users


def publish(notice):
	from school_erp.api.notify import notify

	staff = audience_staff(notice.audience)
	first_line = strip_html(notice.message or "").strip().split("\n")[0][:200]
	prefix = {"Urgent": "URGENT: ", "Important": "Important: "}.get(notice.priority, "")
	notify(
		f"{prefix}{notice.title}", strip_html(notice.message or "")[:1000],
		users=sorted(notice_users(notice)), doc=notice,
		sms=bool(notice.send_sms),
		sms_text=f"{prefix}{notice.title}. {first_line}",
	)
	notice.db_set({"notified": 1, "audience_count": len(staff)}, update_modified=False)


def publish_scheduled():
	"""Daily: send notices whose publish date has arrived."""
	for name in frappe.get_all("School Notice", filters={"notified": 0, "publish_date": ("<=", nowdate())}, pluck="name"):
		publish(frappe.get_doc("School Notice", name))


@frappe.whitelist()
def acknowledge(name):
	"""'Got it' button on the Staff Room dashboard."""
	notice = frappe.get_doc("School Notice", name)
	if not frappe.has_permission("School Notice", "read", notice):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	user = frappe.session.user
	if not any(a.user == user for a in notice.acknowledgements):
		from school_erp.api.notify import staff_for_user

		notice.append("acknowledgements", {"user": user, "staff_member": staff_for_user(user), "acknowledged_on": frappe.utils.now_datetime()})
		notice.acknowledged_count = len(notice.acknowledgements)
		notice.flags.ignore_permissions = True
		notice.save()
	return notice.acknowledged_count
