# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from school_erp.logic.homework import completion


class Homework(Document):
	def validate(self):
		if getdate(self.due_date) < getdate(self.set_on):
			frappe.throw(_("The due date is before the day it was set"))
		if not self.teacher:
			self.teacher = frappe.db.get_value("Teacher", {"user": frappe.session.user})
		in_stream = set(frappe.get_all("Student", filters={"stream": self.stream}, pluck="name"))
		seen = set()
		for r in self.submissions:
			if r.student in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(r.idx, r.student_name or r.student))
			seen.add(r.student)
			if r.student not in in_stream:
				frappe.throw(_("Row {0}: {1} is not in {2}").format(r.idx, r.student_name or r.student, self.stream))
		c = completion([r.status for r in self.submissions])
		self.done_count, self.pending_count, self.completion = c["done"], c["pending"], c["percent"]

	def on_update(self):
		if self.status == "Published" and self.notify_parents and not self.parents_notified:
			from school_erp.api.homework import queue_parent_sms

			queue_parent_sms(self)
