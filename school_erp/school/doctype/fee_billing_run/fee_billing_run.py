# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class FeeBillingRun(Document):
	def validate(self):
		if getdate(self.due_date) < getdate(self.posting_date):
			frappe.throw(_("Due Date cannot be before the Posting Date"))
		if self.stream and self.school_class:
			if frappe.db.get_value("Stream", self.stream, "school_class") != self.school_class:
				frappe.throw(_("Stream {0} is not in class {1}").format(self.stream, self.school_class))
		if not frappe.db.exists("School Fee Structure", {"school_term": self.school_term, "is_active": 1}):
			frappe.throw(_("There is no active fee structure for {0}").format(self.school_term))
		self.status = "Draft"

	def on_submit(self):
		self.db_set("status", "Queued")
		frappe.enqueue(
			"school_erp.api.billing.execute_billing_run",
			queue="long",
			timeout=7200,
			run=self.name,
			enqueue_after_commit=True,
			job_id=f"fee_billing_run::{self.name}",
			deduplicate=True,
		)
		frappe.msgprint(_("Billing has started in the background. This page updates when it finishes."), alert=True)

	def on_cancel(self):
		frappe.throw(
			_("A billing run cannot be cancelled. Cancel or credit individual invoices instead."),
			title=_("Not allowed"),
		)
