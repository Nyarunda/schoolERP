# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class PocketMoneyTransaction(Document):
	def validate(self):
		from school_erp.api.pocket_money import MONEY_ROLES

		if self.transaction_type != "Purchase" and not (MONEY_ROLES & set(frappe.get_roles())):
			frappe.throw(_("Only the Bursar or a School Admin can record a {0}").format(self.transaction_type), frappe.PermissionError)
		self.amount = flt(self.amount, 2)
		if self.amount <= 0:
			frappe.throw(_("The amount must be more than zero"))
		if self.transaction_type in ("Deposit", "Withdrawal"):
			self.mode = self.mode or "Cash"
		else:
			self.mode = None
		self.reference = (self.reference or "").replace(" ", "").upper() or None
		if self.transaction_type == "Deposit" and self.mode in ("M-Pesa", "Bank") and not self.reference:
			frappe.throw(_("Enter the {0} reference so the deposit can be traced").format(self.mode))
		if self.reference:
			dup = frappe.db.get_value("Pocket Money Transaction", {"reference": self.reference, "mode": self.mode,
																   "docstatus": ("<", 2), "name": ("!=", self.name)})
			if dup:
				frappe.throw(_("Reference {0} is already recorded in {1}").format(self.reference, dup))
		self.posting_datetime = self.posting_datetime or now_datetime()
		self.recorded_by = frappe.session.user

	def on_submit(self):
		from school_erp.api.pocket_money import post

		post(self)

	def on_cancel(self):
		from school_erp.api.pocket_money import unpost

		unpost(self)
