# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

from school_erp.logic.boarding import EXEAT_OPEN, exeat_transition_problem


class Exeat(Document):
	def validate(self):
		if get_datetime(self.expected_return) <= get_datetime(self.departure):
			frappe.throw(_("'Back by' must be after 'Leaving'"))
		if self.is_new() and frappe.db.get_value("Student", self.student, "boarding_type") != "Boarder":
			frappe.throw(_("Exeats are for boarders. Use a gate pass for a day scholar."))
		if not self.dormitory:
			self.dormitory = frappe.db.get_value("Boarding Allocation", {"student": self.student, "status": "Active"}, "dormitory")
		before = self.get_doc_before_save()
		problem = exeat_transition_problem(before.status if before else None, self.status)
		if problem:
			frappe.throw(_(problem))
		if self.is_new() and self.status != "Requested" and not self.flags.from_action:
			self.status = "Requested"
		if self.status in EXEAT_OPEN:
			clash = frappe.db.get_value("Exeat", {"student": self.student, "status": ("in", list(EXEAT_OPEN)),
												  "name": ("!=", self.name)}, "name")
			if clash:
				frappe.throw(_("{0} already has an open exeat ({1})").format(self.student_name, clash))

	def after_insert(self):
		from school_erp.api.boarding import alert_approvers

		alert_approvers(self)
