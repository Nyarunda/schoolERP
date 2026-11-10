# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from school_erp.logic.boarding import capacity_problem, gender_problem


class BoardingAllocation(Document):
	def validate(self):
		if self.status == "Ended" and not self.to_date:
			self.to_date = nowdate()
		if self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("The end date is before the start date"))
		if self.status != "Active":
			return
		boarding_type, gender = frappe.db.get_value("Student", self.student, ["boarding_type", "gender"])
		if boarding_type != "Boarder":
			frappe.throw(_("{0} is a day scholar. Change the learner to Boarder first.").format(self.student_name or self.student))
		dorm = frappe.get_cached_doc("Dormitory", self.dormitory)
		if not dorm.is_active:
			frappe.throw(_("{0} is not in use").format(self.dormitory))
		problem = gender_problem(dorm.gender, gender)
		if problem:
			frappe.throw(_(problem))
		other = frappe.db.get_value("Boarding Allocation", {"student": self.student, "status": "Active", "name": ("!=", self.name)},
									"dormitory")
		if other:
			frappe.throw(_("{0} already has a bed in {1}. End that allocation first.").format(self.student_name, other))
		others = frappe.db.count("Boarding Allocation", {"dormitory": self.dormitory, "status": "Active", "name": ("!=", self.name)})
		problem = capacity_problem(dorm.capacity, others)
		if problem:
			frappe.throw(_(problem))
		if self.bed_number:
			self.bed_number = self.bed_number.strip().upper()
			taken = frappe.db.get_value("Boarding Allocation", {"dormitory": self.dormitory, "bed_number": self.bed_number,
																"status": "Active", "name": ("!=", self.name)}, "student_name")
			if taken:
				frappe.throw(_("Bed {0} in {1} is already {2}'s").format(self.bed_number, self.dormitory, taken))

	def on_update(self):
		from school_erp.api.boarding import refresh_dormitory

		refresh_dormitory(self.dormitory)
		before = self.get_doc_before_save()
		if before and before.dormitory != self.dormitory:
			refresh_dormitory(before.dormitory)

	def on_trash(self):
		from school_erp.api.boarding import refresh_dormitory

		refresh_dormitory(self.dormitory, exclude=self.name)
