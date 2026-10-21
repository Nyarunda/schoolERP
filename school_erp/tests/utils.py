"""Test bootstrap used by `bench run-tests --app school_erp`.

Runs the standard ERPNext setup (company, chart of accounts, fiscal year, customer groups,
territories) once, the same way a real school is set up, so tests don't depend on ERPNext's
internal test fixtures, which change between versions.
"""

import frappe
from frappe.utils import getdate, nowdate

TEST_COMPANY = "_Test School Ltd"


def before_tests():
	frappe.clear_cache()
	if not frappe.db.exists("Company", TEST_COMPANY):
		from erpnext.setup.setup_wizard.setup_wizard import setup_complete

		year = getdate(nowdate()).year
		setup_complete(
			frappe._dict(
				{
					"language": "English",
					"country": "Kenya",
					"currency": "KES",
					"company_name": TEST_COMPANY,
					"company_abbr": "_TSL",
					"chart_of_accounts": "Standard",
					"domain": "Education",
					"fy_start_date": f"{year}-01-01",
					"fy_end_date": f"{year}-12-31",
				}
			)
		)
		frappe.db.set_single_value("System Settings", "setup_complete", 1)
		frappe.db.set_default("company", TEST_COMPANY)
		mark_setup_complete()
	frappe.db.commit()


def mark_setup_complete():
	"""Frappe v16 tracks setup per installed app; without this, non-admin users are sent to the Setup Wizard."""
	if frappe.db.has_column("Installed Application", "is_setup_complete"):
		frappe.db.sql("update `tabInstalled Application` set is_setup_complete = 1")
	frappe.clear_cache()
