# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate


class DutyRoster(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date is before From Date"))
		names = [m.staff_member for m in self.members]
		if len(names) != len(set(names)):
			frappe.throw(_("A staff member is listed twice"))
		on_duty = [m.staff_name for m in self.members if m.duty_role == "Teacher on Duty"]
		self.title = f"{formatdate(self.from_date, 'd MMM')} - {formatdate(self.to_date, 'd MMM yyyy')}: {', '.join(on_duty) or 'roster'}"[:140]

	def after_insert(self):
		from school_erp.api.notify import notify

		period = f"{formatdate(self.from_date, 'd MMM')} - {formatdate(self.to_date, 'd MMM')}"
		for m in self.members:
			notify(_("You are {0}: {1}").format(m.duty_role, period),
				   _("You are on the duty roster as {0} from {1} to {2}.").format(m.duty_role, self.from_date, self.to_date),
				   staff=[m.staff_member], doc=self,
				   sms_text=f"You are {m.duty_role} {period}. Remember to submit the daily duty report.")
