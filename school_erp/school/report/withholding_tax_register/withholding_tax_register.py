# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt
"""Supplier payments with tax withheld: what to remit to KRA and what goes on each supplier's certificate."""

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.api.report_utils import col, date_range
from school_erp import licensing


@licensing.licensed("School Expense")
def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = "", {"fd": fd, "td": td}
	if f.supplier:
		cond += " and supplier = %(sup)s"; args["sup"] = f.supplier
	if f.withholding_tax_type:
		cond += " and withholding_tax_type = %(wt)s"; args["wt"] = f.withholding_tax_type
	data = frappe.db.sql(f"""
		select posting_date, 'School Expense' voucher_type, name, coalesce(supplier, payee) supplier, supplier_pin,
			withholding_tax_type, wht_rate, amount - vat_amount taxable_value, wht_amount, vat_wht_amount, amount_paid
		from `tabSchool Expense` where docstatus = 1 and posting_date between %(fd)s and %(td)s
			and (wht_amount > 0 or vat_wht_amount > 0) {cond}""", args, as_dict=True)
	data += _supplier_bills(f, fd, td)
	data.sort(key=lambda r: (r.posting_date, r.name))
	columns = [
		col("posting_date", "Date", "Date", 95), col("voucher_type", "Type", "Data", 120),
		col("name", "Document", "Dynamic Link", 150, "voucher_type"),
		col("supplier", "Supplier", "Data", 170), col("supplier_pin", "KRA PIN", "Data", 120),
		col("withholding_tax_type", "Type", "Data", 170), col("wht_rate", "Rate %", "Percent", 70),
		col("taxable_value", "Taxable Value", "Currency", 120), col("wht_amount", "Withholding Tax", "Currency", 120),
		col("vat_wht_amount", "VAT Withheld", "Currency", 110), col("amount_paid", "Paid to Supplier", "Currency", 130),
	]
	summary = [
		{"label": _("Withholding tax to remit"), "value": sum(flt(r.wht_amount) for r in data), "datatype": "Currency", "indicator": "Red"},
		{"label": _("VAT withheld to remit"), "value": sum(flt(r.vat_wht_amount) for r in data), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Payments"), "value": len(data), "datatype": "Int"},
	]
	return columns, data, None, None, summary


def _supplier_bills(f, fd, td):
	"""Supplier bills (Purchase Invoices) where ERPNext deducted withholding to the school's payable account."""
	s = frappe.get_cached_doc("School Settings")
	if not s.wht_account:
		return []
	cond, args = "", {"fd": fd, "td": td, "acc": s.wht_account}
	if f.supplier:
		cond += " and pi.supplier = %(sup)s"; args["sup"] = f.supplier
	if f.withholding_tax_type:
		cond += " and sup.tax_withholding_category = %(wt)s"; args["wt"] = f.withholding_tax_type
	rows = frappe.db.sql(f"""
		select pi.posting_date, 'Purchase Invoice' voucher_type, pi.name, pi.supplier, sup.tax_id supplier_pin,
			sup.tax_withholding_category withholding_tax_type, pi.net_total taxable_value,
			sum(t.base_tax_amount) wht_amount, 0 vat_wht_amount, pi.grand_total amount_paid
		from `tabPurchase Invoice` pi
		join `tabPurchase Taxes and Charges` t on t.parent = pi.name and t.parenttype = 'Purchase Invoice' and t.account_head = %(acc)s
		left join `tabSupplier` sup on sup.name = pi.supplier
		where pi.docstatus = 1 and pi.posting_date between %(fd)s and %(td)s {cond}
		group by pi.name""", args, as_dict=True)
	for r in rows:
		r.wht_rate = flt(r.wht_amount) / flt(r.taxable_value) * 100 if flt(r.taxable_value) else 0
	return rows
