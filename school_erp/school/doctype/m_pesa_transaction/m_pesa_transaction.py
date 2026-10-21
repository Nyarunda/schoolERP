# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MPesaTransaction(Document):
	def before_insert(self):
		if self.trans_id:
			self.trans_id = self.trans_id.strip().upper()
		if not self.source:
			self.source = "Manual"

	def validate(self):
		if not self.is_new() and self.has_value_changed("amount") and self.status == "Posted":
			frappe.throw(_("A posted payment's amount cannot be changed"))

	def on_trash(self):
		if self.fee_payment and frappe.db.get_value("Fee Payment", self.fee_payment, "docstatus") == 1:
			frappe.throw(_("Cancel Fee Payment {0} first").format(self.fee_payment))
