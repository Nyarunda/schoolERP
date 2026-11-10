# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, nowdate

from school_erp.api import admissions
from school_erp.logic.admissions import requirement_problem, transition_problem

GUEST_FIELDS = ["additional_info", "applying_for_class", "birth_certificate_no", "boarding_type", "date_of_birth", "first_name", "gender", "guardian_email", "guardian_id_number", "guardian_name", "guardian_phone", "last_name", "middle_name", "previous_school", "relation", "residence", "special_needs_details"]


class AdmissionApplication(Document):
	def before_insert(self):
		if frappe.session.user == "Guest" or frappe.flags.in_web_form:
			# a member of the public may only fill in the application itself
			for df in self.meta.fields:
				if df.fieldname not in GUEST_FIELDS and df.fieldtype not in ("Section Break", "Column Break", "Tab Break"):
					self.set(df.fieldname, df.default if df.default else None)
			self.source = "Web Form"
			self.status = "Received"
			admissions.check_open_and_rate_limit(self.guardian_phone)

	def validate(self):
		for field in ("first_name", "middle_name", "last_name", "guardian_name"):
			if self.get(field):
				self.set(field, " ".join(self.get(field).split()).title()[:80])
		self.applicant_name = " ".join(filter(None, [self.first_name, self.middle_name, self.last_name]))
		if self.date_of_birth and getdate(self.date_of_birth) >= getdate(nowdate()):
			frappe.throw(_("Date of birth must be in the past"))
		before = self.get_doc_before_save()
		problem = transition_problem(before.status if before else None, self.status, admitting=bool(self.flags.admitting))
		if problem:
			frappe.throw(_(problem))
		problem = requirement_problem(self.status, self.as_dict())
		if problem:
			frappe.throw(_(problem))

	def after_insert(self):
		admissions.sms_applicant(self, "received_sms")
		admissions.alert_office(self)

	def on_update(self):
		if self.flags.in_insert or not self.has_value_changed("status"):
			return
		template = {"Interview Scheduled": "interview_sms", "Offered": "offer_sms", "Rejected": "regret_sms"}.get(self.status)
		if template:
			admissions.sms_applicant(self, template)
