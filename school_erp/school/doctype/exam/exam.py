# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Exam(Document):
	def autoname(self):
		self.name = f"{self.exam_name.strip()} - {self.school_term}"

	def validate(self):
		if not self.grading_scale:
			self.grading_scale = frappe.db.get_single_value("School Settings", "default_grading_scale")
		if not self.max_marks or self.max_marks <= 0:
			self.max_marks = 100
