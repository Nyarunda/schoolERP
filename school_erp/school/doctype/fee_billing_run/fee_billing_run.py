# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from school_erp.api import billing


class FeeBillingRun(Document):
	def validate(self):
		if getdate(self.due_date) < getdate(self.posting_date):
			frappe.throw(_("Due Date cannot be before the Invoice Date"))
		if self.stream and self.classes:
			stream_class = frappe.db.get_value("Stream", self.stream, "school_class")
			if stream_class not in [c.school_class for c in self.classes]:
				frappe.throw(_("Stream {0} is not in the selected classes").format(self.stream))
		if not frappe.db.exists("School Fee Structure", {"school_term": self.school_term, "is_active": 1}):
			frappe.throw(_("There is no active fee structure for {0}. Create one (or copy last term's) first.").format(self.school_term))
		if self.docstatus == 0:
			self.status = "Draft"
			billing.set_run_totals(self)
		classes = ", ".join(c.school_class for c in self.classes) or _("All classes")
		self.title = f"{self.school_term} - {classes}"[:140]

	@frappe.whitelist()
	def get_students(self):
		"""'Get Students & Fees' button: fill the student list with each student's fee lines and totals."""
		if self.docstatus != 0:
			frappe.throw(_("This run has already been posted"))
		billing.fill_run(self)
		return {"students": self.total_students, "amount": self.total_amount, "already_billed": self.already_billed,
				"no_fees": self.no_fees}

	@frappe.whitelist()
	def set_all(self, include):
		for r in self.students:
			r.include = int(include)
		billing.set_run_totals(self)

	def before_submit(self):
		if not self.students:
			frappe.throw(_("Click 'Get Students & Fees' first"))
		if not any(r.include for r in self.students):
			frappe.throw(_("No students are ticked to invoice"))

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
			now=bool(frappe.flags.in_test),
		)
		if not frappe.flags.in_test:
			frappe.msgprint(_("Posting {0} invoices in the background. This page updates when it finishes.").format(self.total_students), alert=True)

	def on_cancel(self):
		frappe.throw(_("A posted billing run cannot be cancelled. Cancel or credit individual invoices instead."), title=_("Not allowed"))
