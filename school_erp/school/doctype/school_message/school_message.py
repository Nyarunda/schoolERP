# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SchoolMessage(Document):
	def validate(self):
		if self.audience == "Single student" and not self.student:
			frappe.throw(_("Pick the student"))
		if self.audience == "Class" and not self.school_class:
			frappe.throw(_("Pick the class"))
		if self.audience == "Stream" and not self.stream:
			frappe.throw(_("Pick the stream"))
		self.status = "Draft"

	def on_submit(self):
		self.db_set("status", "Queued")
		frappe.enqueue(
			"school_erp.api.messaging.process_school_message",
			queue="long",
			timeout=3600,
			name=self.name,
			enqueue_after_commit=True,
		)
