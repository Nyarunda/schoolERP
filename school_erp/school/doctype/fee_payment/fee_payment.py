# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from school_erp.api import payments
from school_erp.logic.allocation import allocate_payment


class FeePayment(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be more than zero"))
		if not self.mode_of_payment:
			self.mode_of_payment = frappe.db.get_single_value("School Settings", "default_mode_of_payment")
		self.validate_reference()
		self.balance_before = payments.party_balance(self.student)
		if self.manual_allocation:
			self.check_manual_allocation()
		else:
			self.set_allocations()
		self.allocated_total = flt(sum(flt(a.allocated_amount) for a in self.allocations), 2)
		self.unallocated_amount = flt(flt(self.amount) - self.allocated_total, 2)

	def validate_reference(self):
		if not self.reference_no:
			return
		self.reference_no = self.reference_no.strip().upper()
		dup = frappe.db.get_value(
			"Fee Payment", {"reference_no": self.reference_no, "docstatus": 1, "name": ("!=", self.name)}
		)
		if dup:
			frappe.throw(_("Reference {0} was already used on {1}").format(self.reference_no, dup), title=_("Duplicate payment"))

	def set_allocations(self):
		targets = [t.fee_type for t in self.target_fee_types] if self.allocation_method == "Specific fee types" else None
		lines = payments.open_lines(self.student, exclude_payment=self.name)
		allocations, _unallocated = allocate_payment(
			lines, self.amount, target_fee_types=targets, spill_over=bool(self.apply_remainder)
		)
		self.set("allocations", [])
		for a in allocations:
			self.append(
				"allocations",
				{
					"sales_invoice": a["sales_invoice"],
					"school_term": a["school_term"],
					"fee_type": a["fee_type"],
					"outstanding": a["outstanding"],
					"allocated_amount": a["allocated_amount"],
				},
			)

	def check_manual_allocation(self):
		owed = {(l["sales_invoice"], l["fee_type"]): l for l in payments.open_lines(self.student, exclude_payment=self.name)}
		for a in self.allocations:
			line = owed.get((a.sales_invoice, a.fee_type))
			if not line:
				frappe.throw(_("Row {0}: nothing is owed for {1} on {2}").format(a.idx, a.fee_type, a.sales_invoice))
			a.outstanding = line["outstanding"]
			a.school_term = line["school_term"]
			if flt(a.allocated_amount) > flt(line["outstanding"]) + 0.004:
				frappe.throw(_("Row {0}: allocated more than the {1} owed").format(a.idx, line["outstanding"]))
		if sum(flt(a.allocated_amount) for a in self.allocations) > flt(self.amount) + 0.004:
			frappe.throw(_("Allocated total is more than the amount received"))

	def on_submit(self):
		pe = payments.make_payment_entry(self)
		self.db_set({"payment_entry": pe.name, "balance_after": payments.party_balance(self.student)})
		if frappe.db.get_single_value("School Settings", "auto_sms_on_payment"):
			from school_erp import licensing

			if licensing.is_enabled("messaging"):
				frappe.enqueue(
					"school_erp.api.messaging.send_payment_sms",
					payment=self.name,
					enqueue_after_commit=True,
				)

	def before_cancel(self):
		self.ignore_linked_doctypes = ("Payment Entry", "GL Entry", "Payment Ledger Entry")

	def on_cancel(self):
		if self.payment_entry:
			pe = frappe.get_doc("Payment Entry", self.payment_entry)
			if pe.docstatus == 1:
				pe.flags.ignore_permissions = True
				pe.cancel()
		# an auto-posted Paybill payment goes back to the bursar instead of being re-posted by the retry job
		tx = frappe.db.get_value("M-Pesa Transaction", {"fee_payment": self.name})
		if tx:
			frappe.db.set_value("M-Pesa Transaction", tx, {
				"status": "Ignored", "fee_payment": None,
				"error": f"Fee Payment {self.name} was cancelled. Use 'Post to Student' to post it again.",
			})
