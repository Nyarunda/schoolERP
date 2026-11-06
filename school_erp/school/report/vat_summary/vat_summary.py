# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt
"""Monthly VAT figures for the VAT3 return: sales by treatment, output VAT, VAT-able purchases and input VAT."""

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.api.report_utils import bar_chart, col, date_range
from school_erp.api.tax import TEMPLATES
from school_erp.logic.tax import EXEMPT, STANDARD, ZERO_RATED
from school_erp import licensing

KEYS = {STANDARD: "standard", ZERO_RATED: "zero", EXEMPT: "exempt"}


@licensing.licensed("School Expense")
def execute(filters=None):
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	s = frappe.get_cached_doc("School Settings")
	columns = [
		col("month", "Month", "Data", 100), col("standard", "Standard-rated Sales", "Currency", 150),
		col("zero", "Zero-rated Sales", "Currency", 130), col("exempt", "Exempt Sales", "Currency", 130),
		col("output_vat", "Output VAT", "Currency", 120), col("purchases", "VAT-able Purchases", "Currency", 140),
		col("input_vat", "Input VAT", "Currency", 120), col("payable", "VAT Payable", "Currency", 120),
	]
	if not s.vat_registered:
		return columns, [], _("The school is not registered for VAT (School Settings > Tax), so there is no VAT to report.")
	rows = {}

	def row(month):
		return rows.setdefault(month, frappe._dict(month=month, standard=0, zero=0, exempt=0, output_vat=0, purchases=0, input_vat=0))

	treatment_of = {t: k for k, t in TEMPLATES.items()}
	templates = {n: treatment_of.get(t) for n, t in frappe.get_all(
		"Item Tax Template", filters={"company": s.company}, fields=["name", "title"], as_list=True)}
	for r in frappe.db.sql("""select date_format(si.posting_date, '%%Y-%%m') month, sii.item_tax_template tpl, sum(sii.net_amount) net
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.company = %(co)s and si.posting_date between %(fd)s and %(td)s
		group by month, tpl""", {"co": s.company, "fd": fd, "td": td}, as_dict=True):
		row(r.month)[KEYS[templates.get(r.tpl) or EXEMPT]] += flt(r.net)  # no template: no VAT charged

	for field, account, sign in (("output_vat", s.output_vat_account, -1), ("input_vat", s.input_vat_account, 1)):
		for r in frappe.db.sql("""select date_format(posting_date, '%%Y-%%m') month, sum(debit - credit) bal from `tabGL Entry`
			where account = %(acc)s and is_cancelled = 0 and posting_date between %(fd)s and %(td)s group by month""",
			{"acc": account, "fd": fd, "td": td}, as_dict=True):
			row(r.month)[field] += sign * flt(r.bal)

	for r in frappe.db.sql("""select date_format(posting_date, '%%Y-%%m') month, sum(amount - vat_amount) net from `tabSchool Expense`
		where docstatus = 1 and supplier_charged_vat = 1 and posting_date between %(fd)s and %(td)s group by month""",
		{"fd": fd, "td": td}, as_dict=True):
		row(r.month).purchases += flt(r.net)

	for r in frappe.db.sql("""select date_format(pi.posting_date, '%%Y-%%m') month, sum(pi.net_total) net from `tabPurchase Invoice` pi
		where pi.docstatus = 1 and pi.company = %(co)s and pi.posting_date between %(fd)s and %(td)s
			and exists (select 1 from `tabPurchase Taxes and Charges` t where t.parent = pi.name and t.account_head = %(acc)s)
		group by month""", {"co": s.company, "fd": fd, "td": td, "acc": s.input_vat_account}, as_dict=True):
		row(r.month).purchases += flt(r.net)  # supplier bills that carried input VAT

	data = sorted(rows.values(), key=lambda r: r.month)
	for r in data:
		r.payable = flt(r.output_vat - r.input_vat, 2)
	total = sum(r.payable for r in data)
	summary = [
		{"label": _("Output VAT"), "value": sum(r.output_vat for r in data), "datatype": "Currency"},
		{"label": _("Input VAT"), "value": sum(r.input_vat for r in data), "datatype": "Currency"},
		{"label": _("VAT payable") if total >= 0 else _("VAT credit"), "value": abs(total), "datatype": "Currency",
		 "indicator": "Red" if total > 0 else "Green"},
	]
	chart = bar_chart([r.month for r in data], [(_("Output VAT"), [r.output_vat for r in data]), (_("Input VAT"), [r.input_vat for r in data])],
					  money=True) if data else None
	return columns, data, None, chart, summary
