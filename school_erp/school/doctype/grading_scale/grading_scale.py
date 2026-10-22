# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GradingScale(Document):
	def validate(self):
		bands = sorted(self.bands, key=lambda b: b.min_score)
		for b in bands:
			if b.min_score > b.max_score:
				frappe.throw(_("{0}: 'From' is higher than 'To'").format(b.grade))
		for a, b in zip(bands, bands[1:]):
			if b.min_score <= a.max_score:
				frappe.throw(_("Grades {0} and {1} overlap").format(a.grade, b.grade))
			if b.min_score - a.max_score > 1:
				frappe.throw(_("There is a gap between {0} and {1}").format(a.grade, b.grade))
		if bands and bands[0].min_score > 0:
			frappe.throw(_("The lowest grade must start at 0"))
