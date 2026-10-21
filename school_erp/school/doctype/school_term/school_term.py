# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class SchoolTerm(Document):
	def autoname(self):
		self.name = f"{self.term_name.strip()} {self.school_year}"

	def validate(self):
		if getdate(self.end_date) <= getdate(self.start_date):
			frappe.throw(_("End Date must be after Start Date"))
		year = frappe.db.get_value("School Year", self.school_year, ["start_date", "end_date"], as_dict=True)
		if year and not (year.start_date <= getdate(self.start_date) and getdate(self.end_date) <= year.end_date):
			frappe.msgprint(_("Term dates fall outside School Year {0}").format(self.school_year), indicator="orange")
		if self.is_current:
			frappe.db.set_value("School Term", {"name": ("!=", self.name), "is_current": 1}, "is_current", 0)


def get_current_term(on_date=None):
	"""Term marked current, else the term containing the date, else the latest term."""
	on_date = getdate(on_date or nowdate())
	name = frappe.db.get_value("School Term", {"is_current": 1})
	if not name:
		name = frappe.db.get_value(
			"School Term", {"start_date": ("<=", on_date), "end_date": (">=", on_date)}
		)
	if not name:
		rows = frappe.get_all("School Term", order_by="start_date desc", limit=1, pluck="name")
		name = rows[0] if rows else None
	return frappe.get_cached_doc("School Term", name) if name else None
