# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CBCSettings(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if before and before.rubric != self.rubric and frappe.db.exists("Competency Assessment", {"docstatus": 1, "rubric": before.rubric}):
			frappe.msgprint(_("Assessments already made on the {0} rubric stay as they are. Progress reports count only "
							  "assessments made on the rubric chosen here.").format(before.rubric), indicator="orange",
							alert=True)
