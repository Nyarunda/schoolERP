# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from school_erp.logic.billing import SERVICE_CATEGORIES


class SchoolFeeStructure(Document):
	def validate(self):
		seen = set()
		for row in self.items:
			category = frappe.db.get_value("Fee Type", row.fee_type, "category")
			if category in SERVICE_CATEGORIES:
				frappe.throw(
					_("Row {0}: {1} fees are set on the Transport Route or School Activity, not on the fee structure").format(
						row.idx, category
					)
				)
			if row.fee_type in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(row.idx, row.fee_type))
			seen.add(row.fee_type)
		self.total_amount = sum(flt(r.amount) for r in self.items)
		self.title = f"{self.school_term} - {self.school_class or 'All classes'} - {self.boarding_type or 'All'}"
		self.check_duplicate()

	def check_duplicate(self):
		if not self.is_active:
			return
		dup = frappe.db.get_value(
			"School Fee Structure",
			{
				"school_term": self.school_term,
				"school_class": self.school_class or ("is", "not set"),
				"boarding_type": self.boarding_type,
				"is_active": 1,
				"name": ("!=", self.name),
			},
		)
		if dup:
			frappe.throw(_("Active fee structure {0} already covers this term, class and boarding type").format(dup))
