# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from school_erp.api.notify import notify, staff_for_user


class DisciplineIncident(Document):
	def validate(self):
		if not self.reported_by:
			self.reported_by = staff_for_user()
		if self.action_taken == "Suspension":
			if not (self.suspension_from and self.suspension_to):
				frappe.throw(_("Enter the suspension dates"))
			if getdate(self.suspension_to) < getdate(self.suspension_from):
				frappe.throw(_("Suspension end date is before the start date"))

	def after_insert(self):
		if self.severity in ("Major", "Critical"):
			from school_erp.api.staff import head_teacher_users

			notify(_("{0} discipline incident: {1} ({2})").format(self.severity, self.student_name, self.category),
				   self.description, users=head_teacher_users(), doc=self, sms=self.severity == "Critical")
