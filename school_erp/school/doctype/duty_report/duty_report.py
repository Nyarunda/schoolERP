# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate

from school_erp.api import staff as staff_api
from school_erp.api.notify import notify, staff_for_user


class DutyReport(Document):
	def validate(self):
		if not self.staff_member:
			self.staff_member = staff_for_user()
		if not staff_api.is_manager() and self.staff_member != staff_for_user():
			frappe.throw(_("You can only file your own duty report"), frappe.PermissionError)
		dup = frappe.db.get_value("Duty Report", {"staff_member": self.staff_member, "report_date": self.report_date,
												  "docstatus": ("<", 2), "name": ("!=", self.name)})
		if dup:
			frappe.throw(_("A duty report for this day already exists: {0}").format(dup))

	def on_submit(self):
		flags = []
		if self.overall_rating == "Poor":
			flags.append("rated POOR")
		if self.incidents:
			flags.append("incidents reported")
		if not self.lessons_ok:
			flags.append("missed lessons")
		if not self.meals_ok:
			flags.append("meals issue")
		subject = _("Duty report {0}: {1}").format(formatdate(self.report_date, "d MMM"), self.staff_name)
		if flags:
			subject += " - " + ", ".join(flags)
		notify(subject, (self.general_remarks or "") + (f"\n\nIncidents: {self.incidents}" if self.incidents else ""),
			   users=staff_api.duty_report_recipients(), doc=self, sms=bool(flags))
