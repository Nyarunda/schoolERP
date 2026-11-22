"""Stemic's own spending: each expense posts to the books when approved (submitted).

    Stemic Expense submitted -> Journal Entry   Dr <category's expense account> (amount less claimable VAT)
                                                Dr Input VAT (claimable VAT, if any)
                                                Cr M-Pesa Paybill / Stemic Bank / cash (how it was paid)
    cancelled                -> the entry is cancelled

Monthly costs (hosting, salaries...) can repeat: a draft for next month is prepared for an admin to confirm.
"""

import frappe
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

from stemic_control import accounting

CATEGORIES = [
	("Hosting & Servers", "Servers, cloud, backups storage"),
	("SMS & Messaging", "SMS gateway bundles, WhatsApp, email sending"),
	("Domains & SSL", "Domain names, certificates, DNS"),
	("Software & Subscriptions", "Tools and services Stemic subscribes to"),
	("Salaries & Wages", "Staff pay"),
	("Marketing & Sales", "Adverts, printing, events, school visits"),
	("Transport & Travel", "Fuel, fares, accommodation for school visits"),
	("Internet & Phone", "Airtime, data, office internet"),
	("Office & Rent", "Rent, power, office supplies"),
	("Bank & M-Pesa Charges", "Transaction charges"),
	("Professional Fees", "Accountant, lawyer, consultants"),
	("Taxes & Licences", "Business permits, licences (not VAT)"),
	("Other Expenses", "Anything else"),
]
MODES = {"M-Pesa": "mpesa", "Bank Transfer": "bank", "Card": "bank", "Cash": "cash"}
INPUT_VAT = ("Input VAT", "Liability", ["Duties and Taxes"], "Tax")


def ensure_categories(company):
	"""The default categories, each with its own account under Indirect Expenses. Safe to run again."""
	made = {}
	for name, description in CATEGORIES:
		account = accounting._ensure_account(company, name, "Expense", ["Indirect Expenses"])
		if not frappe.db.exists("Stemic Expense Category", name):
			doc = frappe.get_doc({"doctype": "Stemic Expense Category", "category_name": name, "expense_account": account,
								  "description": description, "enabled": 1})
			doc.flags.ignore_permissions = True
			doc.insert()
		made[name] = account
	return made


def check_can_post():
	if not accounting.enabled():
		frappe.throw("Choose the accounting company in Stemic Settings > Accounting first: expenses are posted to the books "
					 "when approved", frappe.ValidationError)


def _expense_account(company, category):
	account = frappe.db.get_value("Stemic Expense Category", category, "expense_account")
	if not account:
		account = accounting._ensure_account(company, category, "Expense", ["Indirect Expenses"])
		frappe.db.set_value("Stemic Expense Category", category, "expense_account", account)
	if frappe.db.get_value("Account", account, "company") != company:
		frappe.throw(f"{category}'s account {account} is not in {company}", frappe.ValidationError)
	return account


def post_expense(doc):
	check_can_post()
	company = accounting.company()
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	vat = flt(doc.vat_amount, 2)
	amount = flt(doc.amount, 2)
	je = frappe.new_doc("Journal Entry")
	je.update({"voucher_type": "Cash Entry" if doc.mode == "Cash" else "Bank Entry", "company": company,
			   "posting_date": doc.posting_date, "cheque_no": doc.reference or doc.name, "cheque_date": doc.posting_date,
			   "user_remark": f"Stemic expense {doc.name}: {doc.category}, {doc.paid_to}: {doc.description}"[:500]})
	je.append("accounts", {"account": _expense_account(company, doc.category), "debit_in_account_currency": flt(amount - vat, 2),
						   "cost_center": cost_center})
	if vat:
		je.append("accounts", {"account": accounting._ensure_account(company, *INPUT_VAT), "debit_in_account_currency": vat,
							   "cost_center": cost_center})
	je.append("accounts", {"account": accounting.account(company, MODES.get(doc.mode, "bank")), "credit_in_account_currency": amount,
						   "cost_center": cost_center})
	doc.db_set("journal_entry", accounting._submit(je), update_modified=False)
	if doc.repeat_monthly:
		doc.db_set("next_repeat_on", add_months(getdate(doc.posting_date), 1), update_modified=False)
	return doc.journal_entry


def cancel_expense(doc):
	accounting._cancel("Journal Entry", doc.get("journal_entry"))
	if doc.repeat_monthly:
		doc.db_set("next_repeat_on", None, update_modified=False)


def daily():
	"""Monthly costs: prepare next month's draft, carrying the repeat on, for an admin to check and submit."""
	from stemic_control.alerts import notify_admins

	made = []
	for name in frappe.get_all("Stemic Expense", filters={"docstatus": 1, "repeat_monthly": 1, "next_repeat_on": ("<=", nowdate())},
							   pluck="name"):
		src = frappe.get_doc("Stemic Expense", name)
		if frappe.db.exists("Stemic Expense", {"repeated_from": name, "docstatus": ("<", 2)}):
			src.db_set("repeat_monthly", 0, update_modified=False)  # the chain carries on from the copy
			continue
		copy = frappe.copy_doc(src)
		copy.update({"posting_date": src.next_repeat_on, "repeated_from": name, "reference": None, "receipt": None,
					 "journal_entry": None, "next_repeat_on": None, "amended_from": None})
		copy.flags.ignore_permissions = True
		copy.insert()
		src.db_set("repeat_monthly", 0, update_modified=False)
		made.append(copy.name)
	if made:
		notify_admins(f"{len(made)} monthly expense(s) ready to confirm", "Open Expenses, check the amount and reference, "
					  "attach the receipt and submit: " + ", ".join(made), sms=False)
	frappe.db.commit()
	return made


@frappe.whitelist(methods=["GET"])
def month_summary(month=None):
	"""Costs by category for a month (YYYY-MM, default this month) against money collected from schools."""
	accounting._admin()
	day = getdate(f"{month}-01") if month else getdate(nowdate())
	start, end = get_first_day(day), get_last_day(day)
	rows = frappe.db.sql("""select category, sum(amount) amount, count(*) n from `tabStemic Expense`
		where docstatus = 1 and posting_date between %s and %s group by category order by amount desc""", (start, end), as_dict=True)
	costs = flt(sum(flt(r.amount) for r in rows), 2)
	collected = flt(frappe.db.sql("""select ifnull(sum(amount), 0) from `tabSaaS Payment` where docstatus = 1
		and payment_date between %s and %s""", (start, end))[0][0], 2)
	commission = flt(frappe.db.sql("""select ifnull(sum(amount), 0) from `tabSaaS Commission` where status != 'Cancelled'
		and earned_on between %s and %s""", (start, end))[0][0], 2)
	return {"month": str(start)[:7], "categories": rows, "costs": costs, "collected": collected, "commission": commission,
			"net": flt(collected - commission - costs, 2)}
