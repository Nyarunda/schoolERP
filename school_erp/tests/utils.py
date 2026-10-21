"""Test bootstrap used by `bench run-tests --app school_erp`."""

import frappe


def before_tests():
	"""Make sure ERPNext's setup wizard has run (company, fiscal year, chart of accounts)."""
	frappe.clear_cache()
	if not frappe.db.a_row_exists("Company"):
		from erpnext.setup.utils import before_tests as erpnext_before_tests

		erpnext_before_tests()
	frappe.db.commit()
