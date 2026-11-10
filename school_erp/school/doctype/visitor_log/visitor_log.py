# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.health import minutes_between, order_problem


class VisitorLog(Document):
	def validate(self):
		self.visitor_name = " ".join((self.visitor_name or "").split()).title()
		self.vehicle_registration = (self.vehicle_registration or "").replace(" ", "").upper() or None
		problem = order_problem(self.time_in, self.time_out)
		if problem:
			frappe.throw(_(problem))
		if self.is_new():
			self.signed_in_by = frappe.session.user
		self.status = "Signed out" if self.time_out else "On premises"
		self.minutes_on_premises = minutes_between(self.time_in, self.time_out)
