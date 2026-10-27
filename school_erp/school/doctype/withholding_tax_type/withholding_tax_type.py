# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class WithholdingTaxType(Document):
	def validate(self):
		if not 0 < flt(self.rate) < 100:
			frappe.throw(_("The rate must be between 0 and 100 percent"))

	def on_update(self):
		from school_erp.api.tax import sync_withholding_categories

		sync_withholding_categories(only=self.name)  # supplier bills use the same rate
