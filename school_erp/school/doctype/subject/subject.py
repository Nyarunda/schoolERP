# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Subject(Document):
	def on_update(self):
		if self.head_of_department and self.has_value_changed("head_of_department"):
			from school_erp.setup.workflows import sync_heads_of_department

			sync_heads_of_department()
