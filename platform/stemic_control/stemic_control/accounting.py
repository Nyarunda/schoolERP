"""Stemic's own books: subscription invoices, payments and agents' commission posted to ERPNext on this site.

Always on once ERPNext is installed here and Stemic Settings > Accounting > Company is set: every invoice, payment,
commission and payout then posts, or is refused with the reason. Each posting happens in the same transaction as the Control Center record, so the two never disagree:
if the accounts refuse (no fiscal year, a closed period), the invoice or payment is refused too, with the reason.

    SaaS Invoice submitted  -> Sales Invoice    Dr Debtors                  Cr Deferred Subscription Income, Output VAT
                                                (released monthly to Subscription Income - <plan> over the period)
    SaaS Payment submitted  -> Payment Entry    Dr M-Pesa Paybill / Bank    Cr Debtors
    Commission earned       -> Journal Entry    Dr Agent Commission         Cr Agent Commission Payable (the agent)
    Commission paid out     -> Journal Entry    Dr Agent Commission Payable Cr M-Pesa Paybill / Bank
    Any of these cancelled  -> its entry is cancelled

Plan prices include VAT (what the school pays), as stemic_control.etims.platform_amounts treats them.
"""

import frappe
from frappe.utils import flt

# account key -> (account name, root type, parent groups to try, account type)
ACCOUNTS = {
    "deferred": ("Deferred Subscription Income", "Liability", ["Current Liabilities"], ""),
    "vat": ("Output VAT", "Liability", ["Duties and Taxes"], "Tax"),
    "commission": ("Agent Commission", "Expense", ["Indirect Expenses"], ""),
    "commission_payable": ("Agent Commission Payable", "Liability", ["Accounts Payable"], "Payable"),
    "mpesa": ("M-Pesa Paybill", "Asset", ["Bank Accounts"], "Bank"),
    "bank": ("Stemic Bank", "Asset", ["Bank Accounts"], "Bank"),
}
INCOME_GROUPS = ["Direct Income"]
# SaaS Payment modes -> the account the money lands in
MODES = {"M-Pesa": "mpesa", "Bank Transfer": "bank", "Cheque": "bank", "Card": "bank", "Other": "bank", "Cash": "cash"}
CUSTOMER_GROUP = "Schools"
SUPPLIER_GROUP = "Sales Agents"
ITEM_GROUP = "Subscriptions"
VAT_TEMPLATE = "Kenya VAT (included in price)"


def enabled():
    if "erpnext" not in frappe.get_installed_apps():
        return False
    return bool(frappe.get_cached_doc("Stemic Settings").get("accounting_company"))  # compulsory once a company is set


def company():
    name = frappe.get_cached_doc("Stemic Settings").get("accounting_company")
    if not name or not frappe.db.exists("Company", name):
        frappe.throw(f"Stemic Settings > Accounting: the company {name or '(none)'} does not exist in ERPNext", frappe.ValidationError)
    return name


# ----------------------------------------------------------------------------- set-up (idempotent)
def _group(company, names, root_type):
    for name in names:
        found = frappe.db.get_value("Account", {"company": company, "account_name": name, "is_group": 1}, "name")
        if found:
            return found
    found = frappe.get_all("Account", filters={"company": company, "root_type": root_type, "is_group": 1},
                           order_by="lft desc", limit=1, pluck="name")
    if not found:
        frappe.throw(f"{company} has no {root_type} group in its chart of accounts", frappe.ValidationError)
    return found[0]


def _ensure_account(company, account_name, root_type, groups, account_type=""):
    found = frappe.db.get_value("Account", {"company": company, "account_name": account_name, "is_group": 0}, "name")
    if found:
        return found
    doc = frappe.get_doc({"doctype": "Account", "company": company, "account_name": account_name, "is_group": 0,
                          "parent_account": _group(company, groups, root_type), "account_type": account_type})
    doc.flags.ignore_permissions = True
    return doc.insert().name


def account(company, key):
    if key == "cash":
        cash = frappe.get_cached_value("Company", company, "default_cash_account")
        if not cash:
            frappe.throw(f"{company} has no default cash account", frappe.ValidationError)
        return cash
    name, root_type, groups, account_type = ACCOUNTS[key]
    return _ensure_account(company, name, root_type, groups, account_type)


def _ensure(doctype, name, values):
    if not frappe.db.exists(doctype, name):
        doc = frappe.get_doc({"doctype": doctype, **values})
        doc.flags.ignore_permissions = True
        doc.insert()
    return name


def _ensure_groups():
    _ensure("Customer Group", CUSTOMER_GROUP, {"customer_group_name": CUSTOMER_GROUP, "parent_customer_group": "All Customer Groups"})
    _ensure("Supplier Group", SUPPLIER_GROUP, {"supplier_group_name": SUPPLIER_GROUP, "parent_supplier_group": "All Supplier Groups"})
    _ensure("Item Group", ITEM_GROUP, {"item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups"})


def plan_item(company, plan):
    """The plan's Item, earning into its own income account, deferred over the invoiced period."""
    income = _ensure_account(company, f"Subscription Income - {plan}", "Income", INCOME_GROUPS)
    code = f"Subscription - {plan}"
    if not frappe.db.exists("Item", code):
        _ensure_groups()
        item = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": ITEM_GROUP,
                               "stock_uom": "Nos", "is_stock_item": 0, "include_item_in_manufacturing": 0,
                               "description": f"{plan} plan, per month", "enable_deferred_revenue": 1})
        item.flags.ignore_permissions = True
        item.insert()
    return code, income


def _vat_template(company, rate):
    abbr = frappe.get_cached_value("Company", company, "abbr")
    name = f"{VAT_TEMPLATE} - {abbr}"
    if not frappe.db.exists("Sales Taxes and Charges Template", name):
        doc = frappe.get_doc({"doctype": "Sales Taxes and Charges Template", "title": VAT_TEMPLATE, "company": company,
                              "taxes": [{"charge_type": "On Net Total", "account_head": account(company, "vat"),
                                         "description": f"VAT {flt(rate):g}%", "rate": flt(rate), "included_in_print_rate": 1}]})
        doc.flags.ignore_permissions = True
        doc.insert()
    return name


def _ensure_modes(company):
    for mode, key in MODES.items():
        target = account(company, key)
        if frappe.db.exists("Mode of Payment", mode):
            doc = frappe.get_doc("Mode of Payment", mode)
        else:
            doc = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": mode,
                                  "type": "Cash" if key == "cash" else "Phone" if key == "mpesa" else "Bank"})
        if not any(row.company == company for row in doc.get("accounts", [])):
            doc.append("accounts", {"company": company, "default_account": target})
        doc.flags.ignore_permissions = True
        doc.save()


@frappe.whitelist(methods=["POST"])
def setup_accounts():
    """Create (once) everything Stemic's postings use in the accounting company. Safe to run again."""
    from stemic_control.billing import _admin

    _admin()
    if "erpnext" not in frappe.get_installed_apps():
        frappe.throw("Install ERPNext on this site first (bench --site <site> install-app erpnext)", frappe.ValidationError)
    company_name = company()
    _ensure_groups()
    used = {key: account(company_name, key) for key in (*ACCOUNTS, "cash")}
    used["vat_template"] = _vat_template(company_name, _vat()[1] or 16)
    _ensure_modes(company_name)
    used["plans"] = {plan: plan_item(company_name, plan)[1] for plan in frappe.get_all("SaaS Plan", pluck="name")}
    from stemic_control import expenses

    used["expense_categories"] = expenses.ensure_categories(company_name)
    settings = frappe.get_doc("Accounts Settings")
    settings.book_deferred_entries_based_on = "Months"
    settings.automatically_process_deferred_accounting_entry = 1
    settings.flags.ignore_permissions = True
    settings.save()
    return used


@frappe.whitelist(methods=["GET"])
def overview():
    """What the Accounting tab shows: whether postings are on, and the accounts they use."""
    from stemic_control.billing import _admin

    _admin()
    if "erpnext" not in frappe.get_installed_apps():
        return {"erpnext": False}
    s = frappe.get_cached_doc("Stemic Settings")
    name = s.get("accounting_company")
    out = {"erpnext": True, "enabled": enabled(), "company": name, "company_exists": bool(name and frappe.db.exists("Company", name))}
    if out["company_exists"]:
        out["accounts"] = {ACCOUNTS[k][0]: frappe.db.get_value("Account", {"company": name, "account_name": ACCOUNTS[k][0], "is_group": 0})
                           for k in ACCOUNTS}
        out["plans"] = {p: frappe.db.get_value("Account", {"company": name, "account_name": f"Subscription Income - {p}", "is_group": 0})
                        for p in frappe.get_all("SaaS Plan", pluck="name")}
        out["unposted_invoices"] = frappe.db.count("SaaS Invoice", {"docstatus": 1, "sales_invoice": ("in", ["", None])})
    return out


# ----------------------------------------------------------------------------- parties
def customer(tenant):
    name = frappe.db.get_value("SaaS Tenant", tenant, "erp_customer")
    if name and frappe.db.exists("Customer", name):
        return name
    _ensure_groups()
    school = frappe.db.get_value("SaaS Tenant", tenant, ["school_name", "slug"], as_dict=True)
    doc = frappe.get_doc({"doctype": "Customer", "customer_name": school.school_name or tenant, "customer_type": "Company",
                          "customer_group": CUSTOMER_GROUP, "territory": _territory()})
    doc.flags.ignore_permissions = True
    doc.insert()
    frappe.db.set_value("SaaS Tenant", tenant, "erp_customer", doc.name, update_modified=False)
    return doc.name


def supplier(agent):
    name = frappe.db.get_value("SaaS Agent", agent, "erp_supplier")
    if name and frappe.db.exists("Supplier", name):
        return name
    _ensure_groups()
    doc = frappe.get_doc({"doctype": "Supplier", "supplier_name": frappe.db.get_value("SaaS Agent", agent, "agent_name") or agent,
                          "supplier_group": SUPPLIER_GROUP, "supplier_type": "Individual"})
    doc.flags.ignore_permissions = True
    doc.insert()
    frappe.db.set_value("SaaS Agent", agent, "erp_supplier", doc.name, update_modified=False)
    return doc.name


def _territory():
    return frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"


def _vat():
    """(treatment, rate): VAT is charged only when Stemic is Standard Rated (Stemic Tax Settings)."""
    s = frappe.get_cached_doc("Stemic Tax Settings")
    treatment = s.get("tax_treatment") or "Standard Rated"
    return treatment, flt(s.get("vat_rate") or 16) if treatment == "Standard Rated" else 0


def _submit(doc):
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.submit()
    return doc.name


def _cancel(doctype, name):
    if name and frappe.db.get_value(doctype, name, "docstatus") == 1:
        doc = frappe.get_doc(doctype, name)
        doc.flags.ignore_permissions = True
        doc.cancel()


# ----------------------------------------------------------------------------- postings
def post_invoice(inv):
    if not enabled() or inv.get("sales_invoice"):
        return None
    company_name = company()
    currency = frappe.get_cached_value("Company", company_name, "default_currency")
    if inv.currency != currency:
        frappe.throw(f"{inv.name} is in {inv.currency}, but {company_name} keeps its books in {currency}", frappe.ValidationError)
    item, income = plan_item(company_name, inv.plan)
    si = frappe.new_doc("Sales Invoice")
    si.update({"company": company_name, "customer": customer(inv.tenant), "posting_date": inv.issue_date, "set_posting_time": 1,
               "due_date": inv.due_date, "currency": currency, "conversion_rate": 1,
               "remarks": f"Stemic subscription: {inv.name}, {inv.plan} plan, {inv.period_start} to {inv.period_end}",
               "po_no": inv.name})
    si.append("items", {"item_code": item, "qty": int(inv.months), "rate": flt(inv.monthly_price), "uom": "Nos",
                        "income_account": income, "enable_deferred_revenue": 1,
                        "deferred_revenue_account": account(company_name, "deferred"),
                        "service_start_date": inv.period_start, "service_end_date": inv.period_end,
                        "description": f"{inv.plan} plan, {inv.months} month(s) from {inv.period_start}"})
    if flt(inv.discount_amount):
        si.apply_discount_on = "Grand Total"
        si.discount_amount = flt(inv.discount_amount)
    treatment, rate = _vat()
    if rate:
        si.taxes_and_charges = _vat_template(company_name, rate)
        si.append("taxes", {"charge_type": "On Net Total", "account_head": account(company_name, "vat"),
                            "description": f"VAT {rate:g}%", "rate": rate, "included_in_print_rate": 1})
    si.flags.ignore_permissions = True
    si.insert()
    if abs(flt(si.grand_total) - flt(inv.total)) > 0.01:
        frappe.throw(f"The accounts would invoice {si.grand_total} for {inv.name}, which is for {inv.total}", frappe.ValidationError)
    si.submit()
    inv.db_set("sales_invoice", si.name, update_modified=False)
    return si.name


def cancel_invoice(inv):
    _cancel("Sales Invoice", inv.get("sales_invoice"))


def post_payment(pay):
    if not enabled() or pay.get("payment_entry"):
        return None
    si_name = frappe.db.get_value("SaaS Invoice", pay.invoice, "sales_invoice")
    if not si_name:
        return None  # the invoice predates posting to accounts: it has no receivable to settle
    si = frappe.get_doc("Sales Invoice", si_name)
    paid_to = account(si.company, MODES.get(pay.mode, "bank"))
    pe = frappe.new_doc("Payment Entry")
    pe.update({"payment_type": "Receive", "company": si.company, "posting_date": pay.payment_date,
               "mode_of_payment": pay.mode if frappe.db.exists("Mode of Payment", pay.mode) else None,
               "party_type": "Customer", "party": si.customer, "paid_from": si.debit_to, "paid_to": paid_to,
               "paid_amount": flt(pay.amount), "received_amount": flt(pay.amount), "source_exchange_rate": 1,
               "target_exchange_rate": 1, "reference_no": pay.reference, "reference_date": pay.payment_date,
               "remarks": f"Stemic subscription payment {pay.name} ({pay.mode} {pay.reference}) for {pay.invoice}"})
    pe.append("references", {"reference_doctype": "Sales Invoice", "reference_name": si.name,
                             "allocated_amount": flt(pay.amount)})
    pay.db_set("payment_entry", _submit(pe), update_modified=False)
    return pay.payment_entry


def cancel_payment(pay):
    _cancel("Payment Entry", pay.get("payment_entry"))


def post_commission(name):
    if not enabled():
        return None
    com = frappe.get_doc("SaaS Commission", name)
    if com.journal_entry or flt(com.amount) <= 0:
        return com.journal_entry
    company_name = company()
    je = frappe.new_doc("Journal Entry")
    je.update({"voucher_type": "Journal Entry", "company": company_name, "posting_date": com.earned_on,
               "user_remark": f"Agent commission {com.name}: {com.rate}% of payment {com.payment} ({com.tenant})"})
    je.append("accounts", {"account": account(company_name, "commission"), "debit_in_account_currency": flt(com.amount),
                           "cost_center": frappe.get_cached_value("Company", company_name, "cost_center")})
    je.append("accounts", {"account": account(company_name, "commission_payable"), "party_type": "Supplier",
                           "party": supplier(com.agent), "credit_in_account_currency": flt(com.amount)})
    com.db_set("journal_entry", _submit(je), update_modified=False)
    return com.journal_entry


def cancel_commission(name):
    _cancel("Journal Entry", frappe.db.get_value("SaaS Commission", name, "journal_entry"))


def post_payout(agent, commissions, reference, paid_on, mode="M-Pesa"):
    """One entry for one payout: the agent's posted commission leaves the payable, paid from M-Pesa or the bank."""
    if not enabled():
        return None
    rows = frappe.get_all("SaaS Commission", filters={"name": ("in", commissions or [""]), "journal_entry": ("is", "set")},
                          fields=["name", "amount"])
    total = flt(sum(flt(r.amount) for r in rows), 2)
    if not total:
        return None
    company_name = company()
    je = frappe.new_doc("Journal Entry")
    je.update({"voucher_type": "Bank Entry", "company": company_name, "posting_date": paid_on, "cheque_no": reference,
               "cheque_date": paid_on, "user_remark": f"Commission payout to {agent}: {reference}"})
    je.append("accounts", {"account": account(company_name, "commission_payable"), "party_type": "Supplier",
                           "party": supplier(agent), "debit_in_account_currency": total})
    je.append("accounts", {"account": account(company_name, MODES.get(mode, "bank")), "credit_in_account_currency": total})
    name = _submit(je)
    for r in rows:
        frappe.db.set_value("SaaS Commission", r.name, "payout_entry", name, update_modified=False)
    return name


def check():
    """Setup Check items for the accounts."""
    from stemic_control.setup_check import _item

    if "erpnext" not in frappe.get_installed_apps():
        return [_item("Accounts", "Post to accounts", None, "ERPNext is not installed on this site: invoices and payments "
                      "are kept in the Control Center only.", "To keep Stemic's books here: bench --site <admin site> install-app erpnext")]
    s = frappe.get_cached_doc("Stemic Settings")
    if not s.get("accounting_company"):
        return [_item("Accounts", "Company", None, "No company chosen: invoices and payments are not posted to the books.",
                      "Stemic Settings > Accounting: choose the company, then Set Up Accounts.")]
    name = s.get("accounting_company")
    if not name or not frappe.db.exists("Company", name):
        return [_item("Accounts", "Company", False, f"{name or 'No company'}: not found in ERPNext.",
                      "Create the company (ERPNext setup) and enter its exact name in Stemic Settings > Accounting.")]
    out = [_item("Accounts", "Company", True, f"Posting to {name}.")]
    from erpnext.accounts.utils import get_fiscal_year

    try:
        get_fiscal_year(frappe.utils.nowdate(), company=name)
        out.append(_item("Accounts", "Fiscal year", True, "Today is in an open fiscal year."))
    except Exception:
        out.append(_item("Accounts", "Fiscal year", False, "No fiscal year covers today: invoices would be refused.",
                         "Create the fiscal year in ERPNext (Accounting > Fiscal Year)."))
    missing = [ACCOUNTS[k][0] for k in ACCOUNTS
               if not frappe.db.get_value("Account", {"company": name, "account_name": ACCOUNTS[k][0], "is_group": 0})]
    out.append(_item("Accounts", "Accounts", not missing, "All set up." if not missing else f"Missing: {', '.join(missing)}",
                     "" if not missing else "Stemic Settings > Accounting > Set Up Accounts."))
    missing = unposted()
    out.append(_item("Accounts", "Everything in the books", not missing,
                     "Every invoice, payment, commission and payout is posted." if not missing else
                     f"{len(missing)} record(s) not posted.", "" if not missing else "Accounting > Post Missing Entries."))
    return out


# ----------------------------------------------------------------------------- nothing outside the books
def unposted():
    """Submitted records with no entry in the books."""
    if not enabled():
        return []
    out = []
    for name, total in frappe.get_all("SaaS Invoice", filters={"docstatus": 1, "sales_invoice": ("in", ["", None])},
                                      fields=["name", "total"], as_list=True):
        out.append({"doctype": "SaaS Invoice", "name": name, "amount": total, "problem": "Invoice not posted"})
    for name, amount in frappe.get_all("SaaS Payment", filters={"docstatus": 1, "payment_entry": ("in", ["", None])},
                                       fields=["name", "amount"], as_list=True):
        out.append({"doctype": "SaaS Payment", "name": name, "amount": amount, "problem": "Payment not posted"})
    for name, amount, status in frappe.get_all("SaaS Commission", filters={"journal_entry": ("in", ["", None]), "amount": (">", 0),
                                                                           "status": ("!=", "Cancelled")},
                                               fields=["name", "amount", "status"], as_list=True):
        out.append({"doctype": "SaaS Commission", "name": name, "amount": amount, "problem": "Commission not posted"})
    for name, amount in frappe.get_all("SaaS Commission", filters={"status": "Paid", "payout_entry": ("in", ["", None])},
                                       fields=["name", "amount"], as_list=True):
        out.append({"doctype": "SaaS Commission", "name": name, "amount": amount, "problem": "Payout not posted"})
    if frappe.db.exists("DocType", "Stemic Expense"):
        for name, amount in frappe.get_all("Stemic Expense", filters={"docstatus": 1, "journal_entry": ("in", ["", None])},
                                           fields=["name", "amount"], as_list=True):
            out.append({"doctype": "Stemic Expense", "name": name, "amount": amount, "problem": "Expense not posted"})
    return out


def _admin():
    from stemic_control.api import _admin as check

    check()


@frappe.whitelist(methods=["GET"])
def ledger_check():
    """Is everything in the books, and do the books agree with what schools owe?"""
    _admin()
    mismatches = []
    if enabled():
        for inv in frappe.get_all("SaaS Invoice", filters={"docstatus": 1, "sales_invoice": ("is", "set")},
                                  fields=["name", "outstanding", "sales_invoice", "school_name"]):
            si = frappe.db.get_value("Sales Invoice", inv.sales_invoice, ["outstanding_amount", "docstatus"], as_dict=True)
            if not si or si.docstatus != 1:
                mismatches.append({"name": inv.name, "problem": f"{inv.sales_invoice} is not a submitted Sales Invoice"})
            elif abs(flt(si.outstanding_amount) - flt(inv.outstanding)) > 0.01:
                mismatches.append({"name": inv.name, "problem": f"{inv.school_name} owes {flt(inv.outstanding):,.2f} here but "
                                   f"{flt(si.outstanding_amount):,.2f} in the books ({inv.sales_invoice})"})
    return {"enabled": enabled(), "company": frappe.get_cached_doc("Stemic Settings").get("accounting_company"),
            "unposted": unposted(), "mismatches": mismatches}


@frappe.whitelist(methods=["POST"])
def post_missing():
    _admin()
    return _post_missing()


def _post_missing():
    """Post every record that is not in the books yet (older invoices, their payments, commissions, payouts), oldest
    first. Each is its own transaction: one refused (a closed period) does not stop the rest."""
    if not enabled():
        frappe.throw("Choose the accounting company in Stemic Settings > Accounting first", frappe.ValidationError)
    done, failed = [], []

    def attempt(label, fn):
        try:
            fn()
            frappe.db.commit()
            done.append(label)
        except Exception as e:
            frappe.db.rollback()
            failed.append({"name": label, "error": str(e)[:300]})

    for name in frappe.get_all("SaaS Invoice", filters={"docstatus": 1, "sales_invoice": ("in", ["", None])},
                               pluck="name", order_by="issue_date asc"):
        attempt(name, lambda name=name: post_invoice(frappe.get_doc("SaaS Invoice", name)))
    for name in frappe.get_all("SaaS Payment", filters={"docstatus": 1, "payment_entry": ("in", ["", None])},
                               pluck="name", order_by="payment_date asc"):
        attempt(name, lambda name=name: post_payment(frappe.get_doc("SaaS Payment", name)))
    for name in frappe.get_all("SaaS Commission", filters={"journal_entry": ("in", ["", None]), "amount": (">", 0),
                                                           "status": ("!=", "Cancelled")}, pluck="name", order_by="earned_on asc"):
        attempt(name, lambda name=name: post_commission(name))
    paid = frappe.get_all("SaaS Commission", filters={"status": "Paid", "payout_entry": ("in", ["", None]),
                                                      "journal_entry": ("is", "set")},
                          fields=["name", "agent", "paid_reference", "paid_on"])
    for key in {(r.agent, r.paid_reference, str(r.paid_on)) for r in paid}:
        names = [r.name for r in paid if (r.agent, r.paid_reference, str(r.paid_on)) == key]
        attempt(f"payout {key[1] or ''} to {key[0]}", lambda key=key, names=names: post_payout(key[0], names, key[1], key[2]))
    if frappe.db.exists("DocType", "Stemic Expense"):
        from stemic_control import expenses

        for name in frappe.get_all("Stemic Expense", filters={"docstatus": 1, "journal_entry": ("in", ["", None])},
                                   pluck="name", order_by="posting_date asc"):
            attempt(name, lambda name=name: expenses.post_expense(frappe.get_doc("Stemic Expense", name)))
    return {"posted": done, "failed": failed}
