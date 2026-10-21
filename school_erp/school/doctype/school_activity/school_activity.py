# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SchoolActivity(Document):
	def validate(self):
		if self.fee_type and frappe.db.get_value("Fee Type", self.fee_type, "category") != "Activity":
			frappe.throw(_("Fee Type {0} must have category Activity").format(self.fee_type))
