"""Fee-type level balances and payment posting."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from school_erp.logic.allocation import split_invoice_paid


def customer_of(student):
	return frappe.db.get_value("Student", student, "customer") or student


def fee_type_priorities():
	return {r.name: r.priority or 10 for r in frappe.get_all("Fee Type", fields=["name", "priority"])}


def explicit_allocations(invoices, exclude_payment=None):
	"""(invoice, fee_type) -> amount allocated by submitted Fee Payments."""
	if not invoices:
		return {}
	cond, args = "", [tuple(invoices)]
	if exclude_payment:
		cond, args = " and fp.name != %s", [tuple(invoices), exclude_payment]
	rows = frappe.db.sql(
		f"""select a.sales_invoice, a.fee_type, sum(a.allocated_amount)
		from `tabFee Payment Allocation` a join `tabFee Payment` fp on fp.name = a.parent
		where fp.docstatus = 1 and a.sales_invoice in %s{cond}
		group by a.sales_invoice, a.fee_type""",
		args,
	)
	return {(r[0], r[1]): flt(r[2]) for r in rows}


def invoice_fee_lines(invoices, exclude_payment=None):
	"""
	For each invoice: lines per fee type with billed, paid and outstanding.
	Returns {invoice: {"info": {...}, "lines": [{fee_type, billed, paid, outstanding, priority}]}}
	"""
	if not invoices:
		return {}
	prio = fee_type_priorities()
	infos = {
		r.name: r
		for r in frappe.get_all(
			"Sales Invoice",
			filters={"name": ("in", invoices)},
			fields=["name", "posting_date", "due_date", "school_term", "grand_total", "outstanding_amount"],
		)
	}
	items = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ("in", invoices)},
		fields=["parent", "fee_type", "item_name", "amount"],
		order_by="idx",
	)
	by_inv = defaultdict(lambda: defaultdict(float))
	for it in items:
		by_inv[it.parent][it.fee_type or it.item_name] += flt(it.amount)
	explicit = explicit_allocations(invoices, exclude_payment)

	out = {}
	for inv, info in infos.items():
		lines = [{"fee_type": ft, "amount": amt, "priority": prio.get(ft, 50)} for ft, amt in by_inv[inv].items()]
		paid_total = flt(info.grand_total) - flt(info.outstanding_amount)
		paid = split_invoice_paid(
			lines, {ft: v for (i, ft), v in explicit.items() if i == inv}, paid_total
		)
		out[inv] = {
			"info": info,
			"lines": [
				{
					"fee_type": l["fee_type"],
					"priority": l["priority"],
					"billed": flt(l["amount"], 2),
					"paid": paid.get(l["fee_type"], 0),
					"outstanding": flt(l["amount"] - paid.get(l["fee_type"], 0), 2),
				}
				for l in sorted(lines, key=lambda x: (x["priority"], x["fee_type"]))
			],
		}
	return out


def open_lines(student, exclude_payment=None):
	"""All fee-type balances still owed by a student, oldest invoice first."""
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer_of(student), "docstatus": 1, "is_return": 0, "outstanding_amount": (">", 0)},
		pluck="name",
	)
	data = invoice_fee_lines(invoices, exclude_payment)
	out = []
	for inv, d in data.items():
		for l in d["lines"]:
			if l["outstanding"] > 0.004:
				out.append(
					{
						"sales_invoice": inv,
						"posting_date": str(d["info"].posting_date),
						"school_term": d["info"].school_term,
						"fee_type": l["fee_type"],
						"priority": l["priority"],
						"outstanding": l["outstanding"],
						"invoice_outstanding": flt(d["info"].outstanding_amount),
					}
				)
	out.sort(key=lambda r: (r["posting_date"], r["sales_invoice"], r["priority"]))
	return out


def party_balance(student):
	"""Net amount the parent owes (negative = credit), straight from the ledger."""
	val = frappe.db.sql(
		"""select coalesce(sum(debit - credit), 0) from `tabGL Entry`
		where party_type = 'Customer' and party = %s and is_cancelled = 0""",
		customer_of(student),
	)
	return flt(val[0][0], 2)


@frappe.whitelist()
def get_open_balances(student):
	frappe.has_permission("Student", "read", student, throw=True)
	lines = open_lines(student)
	summary = defaultdict(float)
	for l in lines:
		summary[l["fee_type"]] += l["outstanding"]
	return {
		"balance": party_balance(student),
		"lines": lines,
		"by_fee_type": [{"fee_type": k, "outstanding": flt(v, 2)} for k, v in summary.items()],
	}


def make_payment_entry(fp):
	"""Create and submit the ERPNext Payment Entry behind a Fee Payment."""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
	from erpnext.accounts.party import get_party_account

	settings = frappe.get_cached_doc("School Settings")
	company = settings.company
	customer = customer_of(fp.student)
	paid_to = get_bank_cash_account(fp.mode_of_payment, company).get("account")
	if not paid_to:
		frappe.throw(_("Set a default account for Mode of Payment {0} in company {1}").format(fp.mode_of_payment, company))

	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.company = company
	pe.posting_date = fp.posting_date
	pe.mode_of_payment = fp.mode_of_payment
	pe.party_type = "Customer"
	pe.party = customer
	pe.student = fp.student
	pe.fee_payment = fp.name
	pe.paid_from = get_party_account("Customer", customer, company)
	pe.paid_to = paid_to
	pe.paid_amount = flt(fp.amount)
	pe.received_amount = flt(fp.amount)
	pe.source_exchange_rate = 1
	pe.target_exchange_rate = 1
	pe.reference_no = fp.reference_no or fp.name
	pe.reference_date = fp.posting_date
	pe.remarks = f"Fee payment {fp.name} for {fp.student_name} ({fp.student})" + (f". {fp.remarks}" if fp.remarks else "")
	if settings.cost_center:
		pe.cost_center = settings.cost_center

	per_invoice = defaultdict(float)
	for a in fp.allocations:
		if flt(a.allocated_amount) > 0:
			per_invoice[a.sales_invoice] += flt(a.allocated_amount)
	for inv, amt in per_invoice.items():
		outstanding = flt(frappe.db.get_value("Sales Invoice", inv, "outstanding_amount"))
		pe.append(
			"references",
			{"reference_doctype": "Sales Invoice", "reference_name": inv, "allocated_amount": min(flt(amt, 2), outstanding)},
		)

	pe.setup_party_account_field()
	pe.set_missing_values()
	pe.set_exchange_rate()
	pe.set_amounts()
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.submit()
	return pe
