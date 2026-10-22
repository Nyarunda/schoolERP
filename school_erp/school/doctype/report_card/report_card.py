# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ReportCard(Document):
	def validate(self):
		dup = frappe.db.get_value("Report Card", {"student": self.student, "exam": self.exam, "name": ("!=", self.name)})
		if dup:
			frappe.throw(_("{0} already has a report card for {1}: {2}").format(self.student, self.exam, dup))
