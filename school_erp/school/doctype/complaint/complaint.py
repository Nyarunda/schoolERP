# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, now_datetime, nowdate, time_diff_in_hours

from school_erp.api import welfare
from school_erp.api.notify import notify, users_for_role

GUEST_FIELDS = {"complainant_name", "phone", "email", "relationship", "student_ref", "category", "subject", "description"}


class Complaint(Document):
	def before_insert(self):
		if frappe.session.user == "Guest" or frappe.flags.in_web_form:
			# a member of the public may only set the complaint fields themselves
			for df in self.meta.fields:
				if df.fieldname not in GUEST_FIELDS and df.fieldtype not in ("Section Break", "Column Break", "Tab Break"):
					self.set(df.fieldname, df.default if df.default else None)
			self.source = "Web Form"
			self.status = "Open"
			self.priority = "Medium"
			self.check_rate_limit()
		if not self.student and self.student_ref:
			from school_erp.api.paybill import find_student

			self.student = find_student(self.student_ref)

	def check_rate_limit(self):
		if not self.phone:
			frappe.throw(_("Please give a phone number so we can update you"))
		from school_erp.logic.text import normalize_phone

		limit = cint(frappe.db.get_single_value("School Settings", "complaint_daily_limit")) or 3
		cc = frappe.db.get_single_value("School Settings", "country_code") or "254"
		mine = normalize_phone(self.phone, cc)
		today = frappe.get_all("Complaint", filters={"creation": (">=", nowdate())}, pluck="phone")
		if sum(1 for p in today if normalize_phone(p, cc) == mine) >= limit:
			frappe.throw(_("Too many complaints from this number today. Please call the school office."))

	def validate(self):
		if self.status in ("Resolved", "Closed") and not self.resolution:
			frappe.throw(_("Write the resolution before marking this complaint {0}").format(self.status))
		if self.status in ("Resolved", "Closed") and not self.resolved_on:
			self.resolved_on = now_datetime()
			self.days_to_resolve = round(time_diff_in_hours(self.resolved_on, self.creation or now_datetime()) / 24, 1)

	def after_insert(self):
		settings = frappe.get_cached_doc("School Settings")
		welfare.sms_complainant(self, settings.complaint_ack_sms)
		heads = [settings.head_teacher_user] if settings.head_teacher_user else users_for_role("Head Teacher")
		notify(_("New complaint {0}: {1} ({2})").format(self.name, self.subject, self.category),
			   self.description, users=heads + users_for_role("School Admin"), doc=self,
			   sms=self.priority in ("High", "Urgent"))

	def on_update(self):
		if self.has_value_changed("assigned_to") and self.assigned_to:
			frappe.share.add("Complaint", self.name, self.assigned_to, write=1, notify=0, flags={"ignore_share_permission": True})
			notify(_("Complaint assigned to you: {0}").format(self.subject), self.description, users=[self.assigned_to], doc=self)
		if self.has_value_changed("status") and self.status == "Resolved":
			welfare.sms_complainant(self, frappe.get_cached_doc("School Settings").complaint_resolved_sms)
