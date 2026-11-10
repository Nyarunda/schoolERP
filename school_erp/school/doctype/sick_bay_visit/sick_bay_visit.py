# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.health import order_problem, temperature_problem


class SickBayVisit(Document):
	def validate(self):
		problem = temperature_problem(self.temperature) or order_problem(self.visit_datetime, self.left_at, "time seen", "time left")
		if problem:
			frappe.throw(_(problem))
		if self.outcome == "Referred to hospital" and not (self.referred_to or "").strip():
			frappe.throw(_("Say which hospital or clinic the learner was referred to"))
		if self.is_new():
			self.attended_by = frappe.session.user
			rec = frappe.db.get_value("Student Health Record", self.student, ["allergies", "chronic_conditions"], as_dict=True)
			if rec:
				self.allergies, self.chronic_conditions = rec.allergies, rec.chronic_conditions

	def after_insert(self):
		from school_erp.api.health import after_visit

		after_visit(self)
