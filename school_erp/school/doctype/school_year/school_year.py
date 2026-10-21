# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class SchoolYear(Document):
	def validate(self):
		if getdate(self.end_date) <= getdate(self.start_date):
			frappe.throw(_("End Date must be after Start Date"))
		if self.is_current:
			frappe.db.set_value("School Year", {"name": ("!=", self.name), "is_current": 1}, "is_current", 0)
