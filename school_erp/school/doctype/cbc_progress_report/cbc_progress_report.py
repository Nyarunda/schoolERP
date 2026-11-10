# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class CBCProgressReport(Document):
	def validate(self):
		dup = frappe.db.get_value("CBC Progress Report", {"student": self.student, "school_term": self.school_term,
														  "name": ("!=", self.name)})
		if dup:
			frappe.throw(_("{0} already has a progress report for {1} ({2})").format(self.student_name, self.school_term, dup))
		if self.status == "Published" and not self.published_on:
			self.published_on = now_datetime()
