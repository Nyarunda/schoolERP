# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TransportRoute(Document):
	def validate(self):
		if frappe.db.get_value("Fee Type", self.fee_type, "category") != "Transport":
			frappe.throw(_("Fee Type {0} must have category Transport").format(self.fee_type))
