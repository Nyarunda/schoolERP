# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.health import order_problem


class GatePass(Document):
	def validate(self):
		problem = order_problem(self.time_out, self.expected_back, "leaving time", "expected return") or \
			order_problem(self.time_out, self.time_back, "leaving time", "time back")
		if problem:
			frappe.throw(_(problem))
		if self.is_new():
			self.approved_by = frappe.session.user
			self.status = "Out"
			open_pass = frappe.db.get_value("Gate Pass", {"student": self.student, "status": "Out"}, "name")
			if open_pass:
				frappe.throw(_("{0} is already out on gate pass {1}. Mark it returned first.").format(self.student_name, open_pass))
		self.status = "Returned" if self.time_back else "Out"

	def after_insert(self):
		from school_erp.api.health import sms_gate_pass

		sms_gate_pass(self)
