# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import nowdate

from school_erp import licensing


class Student(Document):
	def autoname(self):
		settings = frappe.get_cached_doc("School Settings")
		if settings.use_admission_number_as_id and self.admission_number:
			candidate = self.admission_number.strip()
			if frappe.db.exists("Student", candidate) or frappe.db.exists("Customer", candidate):
				frappe.throw(_("Student ID {0} is already in use").format(candidate))
			self.name = candidate
		else:
			self.name = make_autoname(settings.student_id_series or "STU-.YYYY.-.####", doc=self)

	def before_insert(self):
		licensing.check_student_limit()

	def validate(self):
		for f in ("first_name", "middle_name", "last_name"):
			if self.get(f):
				self.set(f, " ".join(self.get(f).split()).title())
		self.student_name = " ".join(filter(None, [self.first_name, self.middle_name, self.last_name]))
		self.validate_admission_number()
		self.validate_leaving()
		self.validate_government_ids()
		self.set_primary_guardian()
		self.validate_services()

	def validate_admission_number(self):
		if self.admission_number and frappe.db.exists(
			"Student", {"admission_number": self.admission_number, "name": ("!=", self.name)}
		):
			frappe.throw(_("Admission number {0} belongs to another student").format(self.admission_number))

	def validate_leaving(self):
		"""Transferred, Left and Graduated learners keep the date they left; a transfer also says where to."""
		if self.status in ("Transferred", "Left", "Graduated"):
			self.leaving_date = self.leaving_date or nowdate()
			if self.status == "Transferred" and not (self.transferred_to or "").strip():
				frappe.throw(_("Enter the school {0} transferred to").format(self.first_name or _("the learner")))
			if self.status != "Transferred":
				self.transferred_to = None
		else:  # back in school
			self.leaving_date = self.transferred_to = self.leaving_reason = None

	def validate_government_ids(self):
		"""UPI, birth certificate and KNEC numbers are stored clean (no spaces, upper case) and never shared by two learners."""
		from school_erp.logic.nemis import clean_id, id_problem

		labels = {"upi_number": _("UPI number"), "birth_certificate_no": _("Birth certificate number"),
				  "assessment_number": _("KNEC assessment number")}
		for field, label in labels.items():
			value = clean_id(self.get(field))
			self.set(field, value or None)
			if not value:
				continue
			problem = id_problem(value, label)
			if problem:
				frappe.throw(_(problem))
			other = frappe.db.get_value("Student", {field: value, "name": ("!=", self.name)}, ["name", "student_name"], as_dict=True)
			if other:
				frappe.throw(_("{0} {1} already belongs to {2} ({3})").format(label, value, other.student_name, other.name))
		if not self.special_needs:
			self.special_needs_details = None

	def set_primary_guardian(self):
		if not self.guardians:
			self.primary_guardian = self.primary_phone = self.primary_email = None
			return
		primaries = [g for g in self.guardians if g.is_primary]
		if len(primaries) > 1:
			frappe.throw(_("Only one guardian can be marked Primary"))
		primary = primaries[0] if primaries else self.guardians[0]
		primary.is_primary = 1
		self.primary_guardian = primary.guardian_name
		self.primary_phone = primary.mobile_no
		self.primary_email = primary.email

	def validate_services(self):
		if self.transport_route:
			licensing.require("transport")
		if self.takes_lunch:
			licensing.require("lunch")
		if self.activities:
			licensing.require("activities")
			names = [a.activity for a in self.activities]
			if len(names) != len(set(names)):
				frappe.throw(_("The same activity is listed twice"))

	def on_update(self):
		self.sync_customer()

	def sync_customer(self):
		"""Every student is a Customer whose ID equals the Student ID, so invoices and payments work natively."""
		settings = frappe.get_cached_doc("School Settings")
		if self.customer and frappe.db.exists("Customer", self.customer):
			current = frappe.db.get_value("Customer", self.customer, ["customer_name", "student"], as_dict=True)
			if current.customer_name != self.student_name or current.student != self.name:
				frappe.db.set_value("Customer", self.customer, {"customer_name": self.student_name, "student": self.name})
			return

		if frappe.db.exists("Customer", self.name):
			frappe.db.set_value("Customer", self.name, "student", self.name)
			self.db_set("customer", self.name)
			return

		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": self.student_name,
				"customer_type": "Individual",
				"customer_group": settings.customer_group or "Students",
				"territory": settings.territory
				or frappe.db.get_single_value("Selling Settings", "territory")
				or "All Territories",
				"student": self.name,
			}
		)
		customer.flags.ignore_permissions = True
		customer.insert(set_name=self.name)
		self.db_set("customer", customer.name)

	def on_trash(self):
		if self.customer and frappe.db.exists("GL Entry", {"party_type": "Customer", "party": self.customer, "is_cancelled": 0}):
			frappe.throw(_("This student has financial records. Set the status to Left instead of deleting."))
		if self.customer:
			frappe.db.set_value("Customer", self.customer, "student", None)


def get_guardian_contacts(student, channel="sms"):
	"""Guardians that opted in to the channel: [{name, phone, email}]."""
	doc = student if isinstance(student, Document) else frappe.get_doc("Student", student)
	out = []
	for g in doc.guardians:
		if channel == "sms" and g.receive_sms and g.mobile_no:
			out.append({"name": g.guardian_name, "phone": g.mobile_no, "email": g.email})
		elif channel == "email" and g.receive_email and g.email:
			out.append({"name": g.guardian_name, "phone": g.mobile_no, "email": g.email})
	return out
