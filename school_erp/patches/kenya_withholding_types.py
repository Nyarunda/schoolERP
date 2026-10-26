import frappe


def execute():
	"""Give existing schools the standard withholding types (they can edit the rates)."""
	frappe.reload_doc("school", "doctype", "withholding_tax_type")
	from school_erp.api.tax import ensure_withholding_types

	ensure_withholding_types()
