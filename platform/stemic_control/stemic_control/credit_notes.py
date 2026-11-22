"""Credit notes and refunds on subscription invoices.

    SaaS Credit Note submitted -> Sales Invoice return (against the invoice's Sales Invoice): reverses the income
                                  (deferred where not yet earned) and VAT, and reduces what the school owes
                                  + refund: Payment Entry (Pay) to the school from M-Pesa / bank / cash
    cancelled                  -> both are cancelled

What the school owes on an invoice = total - credited - (paid - refunded). Only money paid beyond that can be refunded.
A credit on an invoice whose tax invoice is with KRA needs a KRA credit note too: it is flagged and admins alerted.
"""

import frappe
from frappe.utils import flt

from stemic_control import accounting, billing

FILED = ("Pending Submission", "Submitted")


def totals(invoice, exclude=None):
	"""(credited, refunded) on an invoice by its submitted credit notes."""
	row = frappe.db.sql("""select coalesce(sum(amount), 0), coalesce(sum(case when refund = 1 then refund_amount else 0 end), 0)
		from `tabSaaS Credit Note` where invoice = %s and docstatus = 1 and name != %s""", (invoice, exclude or ""))[0]
	return flt(row[0], 2), flt(row[1], 2)


def validate(doc, submitting=False):
	inv = frappe.db.get_value("SaaS Invoice", doc.invoice, ["docstatus", "total", "tenant"], as_dict=True)
	if not inv or inv.docstatus != 1:
		frappe.throw("Choose a submitted invoice", frappe.ValidationError)
	if submitting:
		billing.lock_invoice(doc.invoice)
	amount = flt(doc.amount, 2)
	if amount <= 0:
		frappe.throw("The credit must be more than zero", frappe.ValidationError)
	credited, refunded = totals(doc.invoice, exclude=doc.name)
	room = flt(inv.total - credited, 2)
	if amount > room:
		frappe.throw(f"Only {room:,.2f} of this invoice is left to credit", frappe.ValidationError)
	if doc.refund:
		refund = flt(doc.refund_amount, 2)
		paid = billing.submitted_payments(doc.invoice) if submitting else flt(frappe.db.get_value("SaaS Invoice", doc.invoice, "paid_amount"))
		refundable = flt(max(paid - refunded - (inv.total - credited - amount), 0), 2)
		if refund <= 0:
			frappe.throw("Enter the amount refunded", frappe.ValidationError)
		if refund > min(amount, refundable):
			frappe.throw(f"At most {min(amount, refundable):,.2f} can be refunded: the school has paid {paid:,.2f} and, after this "
						 f"credit, owes {flt(inv.total - credited - amount):,.2f} on the invoice", frappe.ValidationError)
		if not (doc.refund_reference or "").strip():
			frappe.throw("Enter the refund's M-Pesa code or bank reference", frappe.ValidationError)
	else:
		doc.refund_amount = 0


def on_submit(doc):
	post(doc)
	tax = frappe.db.get_value("SaaS eTIMS Invoice", {"saas_invoice": doc.invoice}, ["name", "status"], as_dict=True) \
		if frappe.db.exists("DocType", "SaaS eTIMS Invoice") else None
	if tax and tax.status in FILED:
		doc.db_set("tax_credit_status", "Needed", update_modified=False)
		from stemic_control.alerts import notify_admins

		notify_admins(f"KRA credit note needed for {doc.invoice}",
					  f"Tax invoice {tax.name} is {tax.status} with KRA. Raise a credit note of {flt(doc.amount):,.2f} in eTIMS and "
					  f"enter its number on {doc.name}.", "SaaS Credit Note", doc.name, sms=False)
	if doc.refund and frappe.db.get_value("SaaS Commission", {"invoice": doc.invoice, "status": ("!=", "Cancelled")}):
		from stemic_control.alerts import notify_admins

		notify_admins(f"Refund on {doc.invoice}: check the agent's commission",
					  f"{flt(doc.refund_amount):,.2f} was refunded; the agent was paid commission on this invoice.",
					  "SaaS Credit Note", doc.name, sms=False)
	billing.refresh_invoice(doc.invoice)


def on_cancel(doc):
	accounting._cancel("Payment Entry", doc.get("refund_entry"))
	accounting._cancel("Sales Invoice", doc.get("return_invoice"))
	billing.refresh_invoice(doc.invoice)


def post(doc):
	"""The Sales Invoice return (and refund Payment Entry). Compulsory once an accounting company is set; nothing to do
	when the invoice itself was never posted (Post Missing Entries posts it first)."""
	if not accounting.enabled() or doc.get("return_invoice"):
		return None
	si_name = frappe.db.get_value("SaaS Invoice", doc.invoice, "sales_invoice")
	if not si_name:
		frappe.throw(f"{doc.invoice} is not in the books yet: run Post Missing Entries first", frappe.ValidationError)
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	ret = make_return_doc("Sales Invoice", si_name)
	ret.items = ret.items[:1]
	item = ret.items[0]
	item.qty = -1
	item.rate = flt(doc.amount, 2)  # prices include VAT (the template's tax is included in the print rate)
	item.price_list_rate = item.rate
	item.discount_percentage = 0
	item.discount_amount = 0
	ret.apply_discount_on = None
	ret.discount_amount = 0
	ret.additional_discount_percentage = 0
	ret.posting_date = doc.credit_date
	ret.set_posting_time = 1
	if ret.meta.has_field("update_outstanding_for_self"):
		ret.update_outstanding_for_self = 0  # reduce the original invoice's outstanding
	ret.remarks = f"Stemic credit note {doc.name} for {doc.invoice}: {doc.reason}"
	ret.flags.ignore_permissions = True
	ret.insert()
	if abs(abs(flt(ret.grand_total)) - flt(doc.amount)) > 0.01:
		frappe.throw(f"The books would credit {abs(flt(ret.grand_total)):,.2f}, but the credit note is for {flt(doc.amount):,.2f}",
					 frappe.ValidationError)
	ret.submit()
	doc.db_set("return_invoice", ret.name, update_modified=False)
	if doc.refund and flt(doc.refund_amount):
		doc.db_set("refund_entry", _refund(doc, ret), update_modified=False)
	return ret.name


def _refund(doc, ret):
	company = ret.company
	pe = frappe.new_doc("Payment Entry")
	pe.update({"payment_type": "Pay", "company": company, "posting_date": doc.credit_date, "party_type": "Customer",
			   "party": ret.customer, "paid_from": accounting.account(company, accounting.MODES.get(doc.refund_mode, "bank")),
			   "paid_to": ret.debit_to, "paid_amount": flt(doc.refund_amount), "received_amount": flt(doc.refund_amount),
			   "source_exchange_rate": 1, "target_exchange_rate": 1, "reference_no": doc.refund_reference,
			   "reference_date": doc.credit_date,
			   "mode_of_payment": doc.refund_mode if frappe.db.exists("Mode of Payment", doc.refund_mode) else None,
			   "remarks": f"Refund to {doc.school_name} on credit note {doc.name} ({doc.invoice})"})
	center = accounting._center(doc.tenant, company)
	if center:
		pe.cost_center = center
	return accounting._submit(pe)


def unposted():
	if not accounting.enabled() or not frappe.db.exists("DocType", "SaaS Credit Note"):
		return []
	out = []
	for r in frappe.get_all("SaaS Credit Note", filters={"docstatus": 1}, fields=["name", "amount", "refund", "refund_amount",
																				 "return_invoice", "refund_entry"]):
		if not r.return_invoice:
			out.append({"doctype": "SaaS Credit Note", "name": r.name, "amount": r.amount, "problem": "Credit note not posted"})
		elif r.refund and flt(r.refund_amount) and not r.refund_entry:
			out.append({"doctype": "SaaS Credit Note", "name": r.name, "amount": r.refund_amount, "problem": "Refund not posted"})
	return out


def post_missing(attempt):
	for name in frappe.get_all("SaaS Credit Note", filters={"docstatus": 1, "return_invoice": ("in", ["", None])},
							   pluck="name", order_by="credit_date asc"):
		attempt(name, lambda name=name: post(frappe.get_doc("SaaS Credit Note", name)))
