# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp import licensing
from school_erp.logic.license import MODULES
from school_erp.logic.paybill import is_till


class SchoolSettings(Document):
	def validate(self):
		if self.license_key:
			self.license_key = "".join(self.license_key.split())
		self.refresh_license_fields()
		self.validate_mpesa()
		self.validate_tax()

	def validate_tax(self):
		from school_erp.api import tax
		from school_erp.logic.tax import valid_pin

		self.kra_pin = (self.kra_pin or "").strip().upper()
		if self.kra_pin and not valid_pin(self.kra_pin):
			frappe.throw(_("{0} is not a KRA PIN (it looks like P051234567X)").format(self.kra_pin))
		if self.vat_registered and not self.kra_pin:
			frappe.throw(_("Enter the school's KRA PIN: a VAT-registered school prints it on tax invoices"))
		tax.ensure_accounts(self)

	def validate_mpesa(self):
		if not self.mpesa_enabled:
			return
		if not self.mpesa_callback_token:
			self.mpesa_callback_token = frappe.generate_hash(length=32)
		if self.mpesa_shortcode:
			self.mpesa_shortcode = self.mpesa_shortcode.strip()
			# a Paybill's public number is its short code; a Till's is the till, which differs from its store number
			if not self.paybill_number and not is_till(self.mpesa_account_type):
				self.paybill_number = self.mpesa_shortcode
		if is_till(self.mpesa_account_type):
			self.mpesa_validate_account = 0  # a Till payment has no account number to check
			if not self.paybill_number:
				frappe.msgprint(_("Enter the Till number parents pay to in 'Paybill / Till Number'."), title=_("Till number missing"), indicator="orange")
		if self.mpesa_callback_base_url:
			from school_erp.logic.paybill import url_problems

			self.mpesa_callback_base_url = self.mpesa_callback_base_url.strip().rstrip("/")
			problems = url_problems(self.mpesa_callback_base_url)
			if problems:
				frappe.msgprint("<br>".join(problems), title="Public Site URL", indicator="orange")

	def on_update(self):
		licensing.clear_cache()
		if self.has_value_changed("expense_first_approver_role") or self.has_value_changed("expense_final_approver_role"):
			from school_erp.setup.workflows import make_workflows

			make_workflows()  # approver roles are part of the expense workflow
		if self.has_value_changed("head_teacher_user") and self.head_teacher_user:
			from school_erp.setup.workflows import sync_leave_approvers

			sync_leave_approvers()
		frappe.publish_realtime("school_erp_license_changed", user=frappe.session.user)

	def refresh_license_fields(self):
		from frappe.utils import getdate, nowdate

		from school_erp.logic import license as lic

		state = lic.evaluate(self.license_key or "", licensing.PUBLIC_KEY, getdate(nowdate()), site=frappe.local.site)
		self.license_status = f"{state['status'].title()}: {state['message']}"
		self.licensed_to = state["licensed_to"]
		self.license_expiry = state["expires"]
		self.max_students = state["max_students"]
		self.licensed_modules = ", ".join(MODULES[m] for m in state["modules"] if m in MODULES) or "Core only"


def get_settings():
	return frappe.get_cached_doc("School Settings")
