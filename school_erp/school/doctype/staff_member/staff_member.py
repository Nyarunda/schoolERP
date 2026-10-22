# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

ROLE_FOR_TYPE = {"Teaching": "Teacher", "Driver": "Driver"}


class StaffMember(Document):
	def validate(self):
		self.full_name = " ".join((self.full_name or "").split()).title()
		if self.user and frappe.db.exists("Staff Member", {"user": self.user, "name": ("!=", self.name)}):
			frappe.throw(_("Login {0} is already linked to another staff member").format(self.user))
		if self.reports_to and self.reports_to == self.name:
			frappe.throw(_("A staff member cannot report to themselves"))

	def on_update(self):
		self.sync_teacher()
		self.grant_roles()
		if self.reports_to:
			from school_erp.setup.workflows import sync_leave_approvers

			sync_leave_approvers()

	def sync_teacher(self):
		"""Teaching staff get a Teacher record so they can be put on the timetable."""
		if self.staff_type != "Teaching":
			return
		values = {"teacher_name": self.full_name, "phone": self.phone, "email": self.email, "user": self.user,
				  "staff_member": self.name, "is_active": int(self.status != "Left")}
		if self.teacher and frappe.db.exists("Teacher", self.teacher):
			frappe.db.set_value("Teacher", self.teacher, values)
			return
		t = frappe.get_doc({"doctype": "Teacher", **values})
		t.flags.ignore_permissions = True
		t.insert()
		self.db_set("teacher", t.name)

	def grant_roles(self):
		"""Give the linked login what it needs: Staff (leave), plus Teacher or Driver."""
		if not self.user or self.status == "Left" or self.user in ("Administrator", "Guest"):
			return
		wanted = {"Staff", ROLE_FOR_TYPE.get(self.staff_type)} - {None}
		have = set(frappe.get_roles(self.user))
		missing = wanted - have
		if missing:
			user = frappe.get_doc("User", self.user)
			user.flags.ignore_permissions = True
			user.add_roles(*sorted(missing))
