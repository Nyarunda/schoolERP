# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Stream(Document):
	def autoname(self):
		self.name = f"{self.school_class} {self.stream_name.strip()}"
