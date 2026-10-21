# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from school_erp import licensing
from school_erp.logic.license import MODULES


class SchoolSettings(Document):
	def validate(self):
		if self.license_key:
			self.license_key = "".join(self.license_key.split())
		self.refresh_license_fields()

	def on_update(self):
		licensing.clear_cache()
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
