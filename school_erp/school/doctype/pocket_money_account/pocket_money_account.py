# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PocketMoneyAccount(Document):
	def validate(self):
		# the balance only ever changes through submitted transactions
		self.balance = 0 if self.is_new() else flt(frappe.db.get_value("Pocket Money Account", self.name, "balance"))
		if flt(self.daily_limit) < 0 or flt(self.low_balance_alert) < 0:
			frappe.throw(_("Limits can't be negative"))
		if self.is_frozen and not (self.frozen_reason or "").strip():
			frappe.throw(_("Say why the account is frozen"))
		if not self.is_frozen:
			self.frozen_reason = None
