"""Kenya tax set up per school (School Settings > Tax): VAT on sales and purchases, withholding on supplier payments.

Everything depends on the school's own situation and is off by default:
- not VAT-registered (most schools; education is exempt): invoices carry no VAT, and VAT a supplier charges is part
  of the cost;
- VAT-registered: each Fee Type is Exempt, Zero Rated or Standard Rated; fee amounts stay what the parent pays,
  with any VAT inside them, so balances, statements and receipts are unchanged;
- withholding tax and VAT withholding: deducted from supplier payments at the rates the school keeps.
Arithmetic lives in school_erp.logic.tax.
"""

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.logic import tax as rules

# Item Tax Template title -> VAT treatment (the Standard Rated one carries the school's VAT rate)
TEMPLATES = {rules.STANDARD: "Kenya VAT Standard Rated", rules.ZERO_RATED: "Kenya VAT Zero Rated", rules.EXEMPT: "Kenya VAT Exempt"}

# Withholding types created by School Setup; schools edit or add to them (Withholding Tax Type)
DEFAULT_WITHHOLDING = (
	("Professional or Management Fees", 5, "Consultancy, professional, management and training fees paid to residents"),
	("Contractual Fees", 3, "Payments to resident contractors for works and services under a contract"),
	("Commercial Rent", 10, "Rent for non-residential property (buildings) paid to residents"),
)

# Settings field -> (account name, needed when)
ACCOUNTS = {
	"output_vat_account": ("VAT Output", lambda s: s.vat_registered),
	"input_vat_account": ("VAT Input", lambda s: s.vat_registered),
	"wht_account": ("Withholding Tax Payable", lambda s: s.withhold_tax),
	"vat_wht_account": ("VAT Withholding Payable", lambda s: s.vat_withholding_agent),
}


def _tax_group(company):
	return (
		frappe.db.get_value("Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1})
		or frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 1})
		or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1, "parent_account": ("is", "set")})
	)


def ensure_accounts(settings):
	"""Fill in (creating if needed) the tax accounts the school's settings call for. Called when settings are saved."""
	if not settings.company:
		return
	parent = None
	for field, (account_name, needed) in ACCOUNTS.items():
		if not needed(settings) or settings.get(field):
			continue
		existing = frappe.db.get_value("Account", {"company": settings.company, "account_name": account_name, "is_group": 0})
		if not existing:
			parent = parent or _tax_group(settings.company)
			if not parent:
				frappe.throw(_("No 'Duties and Taxes' group in the chart of accounts: choose the {0} account yourself").format(account_name))
			existing = frappe.get_doc({"doctype": "Account", "account_name": account_name, "parent_account": parent,
									   "company": settings.company, "account_type": "Tax"}).insert(ignore_permissions=True).name
		settings.set(field, existing)
	if settings.vat_registered:
		ensure_item_tax_templates(settings)


def ensure_item_tax_templates(settings):
	"""One ERPNext Item Tax Template per VAT treatment, on the output VAT account, kept at the school's rate."""
	for treatment, title in TEMPLATES.items():
		rate = flt(settings.vat_rate) if treatment == rules.STANDARD else 0
		name = frappe.db.get_value("Item Tax Template", {"title": title, "company": settings.company})
		doc = frappe.get_doc("Item Tax Template", name) if name else frappe.get_doc(
			{"doctype": "Item Tax Template", "title": title, "company": settings.company})
		if [(t.tax_type, flt(t.tax_rate)) for t in doc.taxes] == [(settings.output_vat_account, rate)]:
			continue
		doc.set("taxes", [{"tax_type": settings.output_vat_account, "tax_rate": rate}])
		doc.save(ignore_permissions=True)


def template_for(settings, treatment):
	return frappe.db.get_value("Item Tax Template", {"title": TEMPLATES.get(treatment or rules.EXEMPT), "company": settings.company})


def apply_vat(si, settings, fee_types):
	"""A VAT-registered school's fee invoice: each line gets its treatment's template; one inclusive VAT row is added
	only if a line is Standard Rated. The invoice total stays the sum of the fee amounts."""
	if not settings.vat_registered:
		return
	treatments = {row.fee_type: (fee_types.get(row.fee_type) or {}).get("vat_treatment") or rules.EXEMPT for row in si.items}
	if set(treatments.values()) == {rules.EXEMPT}:
		return  # an all-exempt bill (most fee bills) shows no VAT line at all; the VAT Summary counts it as exempt
	for row in si.items:
		row.item_tax_template = template_for(settings, treatments[row.fee_type])
	if rules.STANDARD in treatments.values():
		si.append("taxes", {
			"charge_type": "On Net Total", "account_head": settings.output_vat_account,
			"description": _("VAT {0}%").format(flt(settings.vat_rate)), "rate": flt(settings.vat_rate),
			"included_in_print_rate": 1, "cost_center": settings.cost_center,
		})


def expense_breakdown(doc, settings):
	"""Fill an expense's VAT, withholding and amount-paid fields from the school's tax settings."""
	wht_rate = 0
	if settings.withhold_tax and doc.withholding_tax_type:
		wht_rate = flt(frappe.db.get_value("Withholding Tax Type", doc.withholding_tax_type, "rate"))
	elif doc.withholding_tax_type:
		frappe.throw(_("Withholding tax is switched off in School Settings > Tax"))
	split = rules.expense_split(
		doc.amount, supplier_charged_vat=bool(doc.supplier_charged_vat), vat_rate=settings.vat_rate or 16,
		school_vat_registered=bool(settings.vat_registered), wht_rate=wht_rate,
		vat_wht_rate=flt(settings.vat_wht_rate) if settings.vat_withholding_agent else 0,
	)
	doc.vat_amount, doc.input_vat = split["vat"], split["input_vat"]
	doc.wht_rate, doc.wht_amount, doc.vat_wht_amount = wht_rate, split["wht"], split["vat_wht"]
	doc.amount_paid = split["paid"]
	if (split["wht"] or split["vat_wht"]) and not (doc.supplier or doc.supplier_pin):
		frappe.throw(_("Choose the supplier (or enter their KRA PIN) when tax is withheld: it goes on their withholding certificate"))
	return split


def journal_lines(doc, settings, expense_account, paid_from):
	"""(account, debit, credit) rows for an approved expense: cost and claimable VAT against what was paid and withheld."""
	split = expense_breakdown(doc, settings)
	rows = [(expense_account, split["expense"], 0)]
	if split["input_vat"]:
		rows.append((settings.input_vat_account, split["input_vat"], 0))
	rows.append((paid_from, 0, split["paid"]))
	if split["wht"]:
		rows.append((settings.wht_account, 0, split["wht"]))
	if split["vat_wht"]:
		rows.append((settings.vat_wht_account, 0, split["vat_wht"]))
	return [(account, flt(dr, 2), flt(cr, 2)) for account, dr, cr in rows]


def ensure_withholding_types():
	created = []
	for name, rate, description in DEFAULT_WITHHOLDING:
		if not frappe.db.exists("Withholding Tax Type", name):
			frappe.get_doc({"doctype": "Withholding Tax Type", "tax_type_name": name, "rate": rate, "is_active": 1,
							"description": description}).insert(ignore_permissions=True)
			created.append(name)
	return created
