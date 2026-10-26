# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt
"""Supplier payments with tax withheld: what to remit to KRA and what goes on each supplier's certificate."""

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.api.report_utils import col, date_range


def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = "", {"fd": fd, "td": td}
	if f.supplier:
		cond += " and supplier = %(sup)s"; args["sup"] = f.supplier
	if f.withholding_tax_type:
		cond += " and withholding_tax_type = %(wt)s"; args["wt"] = f.withholding_tax_type
	data = frappe.db.sql(f"""
		select posting_date, name, coalesce(supplier, payee) supplier, supplier_pin, withholding_tax_type, wht_rate,
			amount - vat_amount taxable_value, wht_amount, vat_wht_amount, amount_paid, journal_entry
		from `tabSchool Expense` where docstatus = 1 and posting_date between %(fd)s and %(td)s
			and (wht_amount > 0 or vat_wht_amount > 0) {cond}
		order by posting_date""", args, as_dict=True)
	columns = [
		col("posting_date", "Date", "Date", 95), col("name", "Expense", "Link", 140, "School Expense"),
		col("supplier", "Supplier", "Data", 170), col("supplier_pin", "KRA PIN", "Data", 120),
		col("withholding_tax_type", "Type", "Data", 170), col("wht_rate", "Rate %", "Percent", 70),
		col("taxable_value", "Taxable Value", "Currency", 120), col("wht_amount", "Withholding Tax", "Currency", 120),
		col("vat_wht_amount", "VAT Withheld", "Currency", 110), col("amount_paid", "Paid to Supplier", "Currency", 130),
		col("journal_entry", "Journal Entry", "Link", 140, "Journal Entry"),
	]
	summary = [
		{"label": _("Withholding tax to remit"), "value": sum(flt(r.wht_amount) for r in data), "datatype": "Currency", "indicator": "Red"},
		{"label": _("VAT withheld to remit"), "value": sum(flt(r.vat_wht_amount) for r in data), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Payments"), "value": len(data), "datatype": "Int"},
	]
	return columns, data, None, None, summary
