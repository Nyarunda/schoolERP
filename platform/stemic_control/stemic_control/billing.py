"""Subscription billing: invoices per school per period, payments against them, and agents' commission.

Invoice (plan price x months) -> Payment(s) -> when fully paid, the subscription runs to the end of the invoiced
period and becomes Active -> the school's agent earns commission on each payment (Stemic Settings decides whether
on every payment or the first only). Cancelling a payment reverses all of that. Daily: unpaid invoices past their
due date become Overdue (and the subscription Past Due once it has ended), and renewal invoices are raised ahead of
the end date.
"""

import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from stemic_control import policy

OPEN = ("Unpaid", "Partly Paid", "Overdue")


def settings():
    s = frappe.get_cached_doc("Stemic Settings") if frappe.db.exists("DocType", "Stemic Settings") else frappe._dict()
    return frappe._dict(
        currency=s.get("currency") or "KES", billing_months=s.get("billing_months") or 12,
        payment_terms_days=s.get("payment_terms_days") if s.get("payment_terms_days") is not None else 14,
        renewal_notice_days=s.get("renewal_notice_days") if s.get("renewal_notice_days") is not None else 30,
        commission_basis=s.get("commission_basis") or "Every payment",
        payment_instructions=s.get("payment_instructions") or "",
    )


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


def period_end(start, months):
    return add_days(add_months(getdate(start), int(months)), -1)


def next_period_start(sub):
    """A renewal continues from the day after the current end; a lapsed or new subscription starts today."""
    today = getdate(nowdate())
    if sub.ends_on and getdate(sub.ends_on) >= today:
        return add_days(getdate(sub.ends_on), 1)
    return today


# ----------------------------------------------------------------------------- invoices
def compute_invoice(doc):
    """Fill an invoice's derived fields (called from SaaSInvoice.validate)."""
    sub = frappe.db.get_value("SaaS Subscription", doc.subscription, ["tenant", "plan", "agent"], as_dict=True)
    if not sub:
        frappe.throw("Unknown subscription", frappe.ValidationError)
    if doc.tenant and doc.tenant != sub.tenant:
        frappe.throw("This subscription belongs to another school", frappe.ValidationError)
    doc.tenant, doc.plan, doc.agent = sub.tenant, sub.plan, sub.agent
    if int(doc.months or 0) < 1:
        frappe.throw("Invoice at least one month", frappe.ValidationError)
    if doc.monthly_price in (None, ""):
        doc.monthly_price = frappe.db.get_value("SaaS Plan", sub.plan, "monthly_price") or 0
    doc.currency = doc.currency or settings().currency
    doc.period_end = period_end(doc.period_start, doc.months)
    doc.amount = flt(doc.monthly_price) * int(doc.months)
    if flt(doc.discount_amount) < 0 or flt(doc.discount_amount) > doc.amount:
        frappe.throw("The discount must be between zero and the invoice amount", frappe.ValidationError)
    doc.total = flt(doc.amount - flt(doc.discount_amount), 2)
    if doc.total <= 0:
        frappe.throw("An invoice must be for more than zero", frappe.ValidationError)
    if not doc.due_date:
        doc.due_date = add_days(doc.issue_date or nowdate(), settings().payment_terms_days)
    if getdate(doc.due_date) < getdate(doc.issue_date):
        frappe.throw("The due date cannot be before the invoice date", frappe.ValidationError)
    if doc.docstatus == 0:
        doc.paid_amount, doc.outstanding = 0, doc.total


def submitted_payments(invoice, exclude=None):
    """The total of an invoice's submitted payments, as committed now.

    A locking read: under MariaDB's REPEATABLE READ a plain SELECT returns the snapshot taken at the transaction's
    first read, so a client that waited for the invoice lock would still miss the payment that was committed while it
    waited. FOR UPDATE reads the latest committed rows (and holds them until this transaction ends)."""
    return flt(frappe.db.sql(
        "SELECT COALESCE(SUM(amount), 0) FROM `tabSaaS Payment` WHERE invoice = %s AND docstatus = 1 AND name != %s FOR UPDATE",
        (invoice, exclude or ""))[0][0], 2)


def refresh_invoice(name):
    """Paid amount, outstanding and status from the invoice's submitted payments, under the invoice lock."""
    lock_invoice(name)
    inv = frappe.get_doc("SaaS Invoice", name)
    paid = submitted_payments(name)
    outstanding = flt(inv.total - paid, 2)
    if inv.docstatus == 2:
        status = "Cancelled"
    elif outstanding <= 0:
        status = "Paid"
    elif getdate(inv.due_date) < getdate(nowdate()):
        status = "Overdue"
    else:
        status = "Partly Paid" if paid else "Unpaid"
    inv.db_set({"paid_amount": paid, "outstanding": max(outstanding, 0), "status": status})
    return inv.reload()


def open_invoice(subscription):
    return frappe.db.get_value("SaaS Invoice", {"subscription": subscription, "docstatus": 1, "status": ("in", OPEN)}, "name")


@frappe.whitelist(methods=["POST"])
def create_invoice(subscription, months=None, period_start=None, discount_amount=0, description=None):
    """Invoice a subscription's next period (plan price x months). Refused while an earlier invoice is unpaid."""
    _admin()
    return _create_invoice(subscription, months, period_start, discount_amount, description)


def _create_invoice(subscription, months=None, period_start=None, discount_amount=0, description=None):
    # All creation paths (including the scheduler) serialize by subscription.
    # InnoDB holds this row lock until the surrounding request commits.
    if not frappe.db.sql("SELECT name FROM `tabSaaS Subscription` WHERE name = %s FOR UPDATE", (subscription,)):
        frappe.throw("Unknown subscription", frappe.ValidationError)
    sub = frappe.get_doc("SaaS Subscription", subscription)
    if sub.status == "Cancelled":
        frappe.throw("A cancelled subscription cannot be invoiced", frappe.ValidationError)
    existing = open_invoice(sub.name)
    if existing:
        frappe.throw(f"{existing} for this subscription is still unpaid. Collect or cancel it first.", frappe.ValidationError)
    inv = frappe.get_doc({
        "doctype": "SaaS Invoice", "tenant": sub.tenant, "subscription": sub.name, "issue_date": nowdate(),
        "period_start": period_start or next_period_start(sub), "months": int(months or settings().billing_months),
        "discount_amount": flt(discount_amount), "description": description,
    })
    inv.insert(ignore_permissions=True)
    inv.submit()
    return inv.name



def validate_invoice_for_submit(doc):
    """Guard the form-submit path too; users can submit invoices outside the create API."""
    if not frappe.db.sql(
        "SELECT name FROM `tabSaaS Subscription` WHERE name = %s FOR UPDATE",
        (doc.subscription,),
    ):
        frappe.throw("Unknown subscription", frappe.ValidationError)
    conflicting = frappe.db.get_value(
        "SaaS Invoice",
        {
            "subscription": doc.subscription,
            "docstatus": 1,
            "status": ("in", OPEN),
            "name": ("!=", doc.name),
        },
        "name",
    )
    if conflicting:
        frappe.throw(
            f"Invoice {conflicting} is still unpaid; cannot submit another invoice",
            frappe.ValidationError,
        )


# ----------------------------------------------------------------------------- payments
def validate_payment(doc):
    inv = frappe.db.get_value("SaaS Invoice", doc.invoice, ["docstatus", "outstanding", "tenant"], as_dict=True)
    if not inv or inv.docstatus != 1:
        frappe.throw("Payments are recorded against a submitted invoice", frappe.ValidationError)
    if flt(doc.amount) <= 0:
        frappe.throw("The amount must be more than zero", frappe.ValidationError)
    if flt(doc.amount) > flt(inv.outstanding) + 0.005:
        frappe.throw(f"That is more than the {flt(inv.outstanding):,.2f} still owed on {doc.invoice}", frappe.ValidationError)
    doc.reference = (doc.reference or "").strip().upper()
    if not doc.reference:
        frappe.throw("A non-empty payment reference is required", frappe.ValidationError)
    clash = frappe.db.get_value("SaaS Payment", {"mode": doc.mode, "reference": doc.reference, "docstatus": 1, "name": ("!=", doc.name)})
    if clash:
        frappe.throw(f"{doc.mode} reference {doc.reference} is already recorded on {clash}", frappe.ValidationError)
    doc.tenant = inv.tenant



def lock_invoice(invoice):
    """InnoDB row lock shared by payment submit/cancel and invoice cancellation. Returns the invoice's docstatus as
    committed now (a locking read), so a caller that waited sees a cancellation made meanwhile."""
    row = frappe.db.sql("SELECT docstatus FROM `tabSaaS Invoice` WHERE name = %s FOR UPDATE", (invoice,))
    if not row:
        frappe.throw("Unknown invoice", frappe.ValidationError)
    return row[0][0]


def has_submitted_payment(invoice):
    """Locking read: a payment committed while we waited for the invoice lock is seen."""
    return bool(frappe.db.sql("SELECT name FROM `tabSaaS Payment` WHERE invoice = %s AND docstatus = 1 LIMIT 1 FOR UPDATE",
                              (invoice,)))


def validate_payment_for_submit(doc):
    """Recheck the live balance under an invoice row lock immediately before submit.

    Do not trust the previously calculated outstanding field: the same invoice
    may have received another payment since the draft was validated.
    """
    if lock_invoice(doc.invoice) != 1:
        frappe.throw("Invoice is not submitted", frappe.ValidationError)
    paid = submitted_payments(doc.invoice, exclude=doc.name)  # locking read: sees payments committed while we waited
    total = frappe.db.get_value("SaaS Invoice", doc.invoice, "total")
    remaining = flt(flt(total) - flt(paid), 2)
    if remaining <= 0 or flt(doc.amount) > remaining + 0.005:
        frappe.throw(
            f"Payment exceeds the current invoice balance of {remaining:,.2f}",
            frappe.ValidationError,
        )
    validate_payment(doc)
    # Drafts do not reserve references; the unique DB key is claimed on submit.
    doc.reference_key = reference_key(doc.mode, doc.reference)


def reference_key(mode, reference):
    """The unique key for a payment reference: the same M-Pesa code (or bank reference) is recorded once per mode."""
    import hashlib

    return hashlib.sha256(f"{mode}|{(reference or '').strip().upper()}".encode()).hexdigest()


def apply_payment(doc):
    """A payment was submitted: update its invoice, and if that is now paid, extend the subscription; pay commission."""
    inv = refresh_invoice(doc.invoice)
    if flt(inv.paid_amount) > flt(inv.total) + 0.005:
        frappe.throw("Submitted payments exceed invoiced amount; transaction rolled back", frappe.ValidationError)
    if inv.status == "Paid":
        sub = frappe.get_doc("SaaS Subscription", inv.subscription)
        if not sub.ends_on or getdate(inv.period_end) > getdate(sub.ends_on):
            sub.ends_on = inv.period_end
        if sub.status != "Active" and policy.can_move(policy.SUBSCRIPTION_TRANSITIONS, sub.status, "Active"):
            sub.status = "Active"
        sub.external_payment_ref = doc.reference
        sub.flags.ignore_permissions = True
        sub.save()
    earn_commission(doc, inv)


def reverse_payment(doc):
    """A payment was cancelled: its commission goes, the invoice reopens, and the subscription loses the period.
    Its reference is released, so the same M-Pesa code can be recorded again against the right invoice."""
    doc.db_set("reference_key", None)
    for name, status in frappe.get_all("SaaS Commission", filters={"payment": doc.name}, fields=["name", "status"], as_list=True):
        if status == "Paid":
            frappe.throw(f"Commission {name} on this payment was already paid to the agent. Recover it first, then cancel.",
                         frappe.ValidationError)
        frappe.db.set_value("SaaS Commission", name, "status", "Cancelled")
    inv = refresh_invoice(doc.invoice)
    if inv.status != "Paid":
        sub = frappe.get_doc("SaaS Subscription", inv.subscription)
        if sub.ends_on and getdate(sub.ends_on) == getdate(inv.period_end):
            sub.ends_on = add_days(getdate(inv.period_start), -1)
            sub.flags.ignore_permissions = True
            sub.save()


@frappe.whitelist(methods=["POST"])
def record_payment(invoice, amount, mode, reference, payment_date=None, notes=None):
    """Record money received against an invoice (submitted at once)."""
    _admin()
    pay = frappe.get_doc({"doctype": "SaaS Payment", "invoice": invoice, "amount": flt(amount), "mode": mode,
                          "reference": reference, "payment_date": payment_date or nowdate(), "notes": notes})
    pay.insert(ignore_permissions=True)
    pay.submit()
    inv = frappe.db.get_value("SaaS Invoice", invoice, ["status", "outstanding", "subscription"], as_dict=True)
    return {"payment": pay.name, "invoice_status": inv.status, "outstanding": inv.outstanding,
            "ends_on": str(frappe.db.get_value("SaaS Subscription", inv.subscription, "ends_on"))}


# ----------------------------------------------------------------------------- commission
def earn_commission(payment, inv):
    if not inv.agent:
        return None
    agent = frappe.db.get_value("SaaS Agent", inv.agent, ["status", "commission_rate"], as_dict=True)
    if not agent or agent.status != "Active" or flt(agent.commission_rate) <= 0:
        return None
    if settings().commission_basis == "First payment only" and frappe.db.exists(
            "SaaS Commission", {"tenant": inv.tenant, "status": ("!=", "Cancelled"), "payment": ("!=", payment.name)}):
        return None
    com = frappe.get_doc({
        "doctype": "SaaS Commission", "agent": inv.agent, "tenant": inv.tenant, "invoice": inv.name, "payment": payment.name,
        "earned_on": payment.payment_date, "base_amount": flt(payment.amount), "rate": flt(agent.commission_rate),
        "amount": flt(flt(payment.amount) * flt(agent.commission_rate) / 100, 2), "status": "Due",
    })
    com.insert(ignore_permissions=True)
    return com.name


@frappe.whitelist(methods=["POST"])
def pay_commissions(agent, reference, paid_on=None):
    """Mark all of an agent's due commission as paid out in one payout (e.g. one M-Pesa transfer)."""
    _admin()
    if not (reference or "").strip():
        frappe.throw("Enter the payout reference", frappe.ValidationError)
    names = frappe.get_all("SaaS Commission", filters={"agent": agent, "status": "Due"}, pluck="name")
    for name in names:
        frappe.db.set_value("SaaS Commission", name, {"status": "Paid", "paid_on": paid_on or nowdate(),
                                                     "paid_reference": reference.strip()})
    total = flt(sum(frappe.get_all("SaaS Commission", filters={"name": ("in", names or [""])}, pluck="amount")), 2)
    return {"paid": len(names), "total": total}


# ----------------------------------------------------------------------------- daily
def daily():
    """Scheduler: Overdue invoices, Past Due subscriptions, and renewal invoices ahead of the end date."""
    today = getdate(nowdate())
    for name in frappe.get_all("SaaS Invoice", filters={"docstatus": 1, "status": ("in", ["Unpaid", "Partly Paid"]),
                                                        "due_date": ("<", today)}, pluck="name"):
        inv = refresh_invoice(name)
        sub = frappe.get_doc("SaaS Subscription", inv.subscription)
        if sub.status == "Active" and sub.ends_on and getdate(sub.ends_on) < today:
            sub.status = "Past Due"
            sub.flags.ignore_permissions = True
            sub.save()
    notice = int(settings().renewal_notice_days or 0)
    if notice:
        for sub in frappe.get_all("SaaS Subscription", filters={"status": ("in", ["Active", "Past Due", "Grace"]),
                                                               "ends_on": ("between", [today, add_days(today, notice)])},
                                  pluck="name"):
            if not open_invoice(sub):
                try:
                    _create_invoice(sub)
                except frappe.ValidationError:
                    frappe.log_error(title=f"Renewal invoice not raised for {sub}")
    frappe.db.commit()


def ledger_mismatches(limit=50):
    """Invoices whose stored figures disagree with their payment ledger (submitted payments). Detection only: the
    ledger is authoritative and an operator decides what to do, so nothing is changed here."""
    rows = frappe.db.sql("""
        SELECT i.name, i.tenant, i.school_name, i.docstatus, i.total, i.paid_amount, i.outstanding,
               COALESCE(SUM(CASE WHEN p.docstatus = 1 THEN p.amount END), 0) AS ledger
        FROM `tabSaaS Invoice` i LEFT JOIN `tabSaaS Payment` p ON p.invoice = i.name
        WHERE i.docstatus IN (1, 2)
        GROUP BY i.name
        HAVING (i.docstatus = 1 AND (ABS(i.paid_amount - ledger) >= 0.005
                                     OR ABS(i.outstanding - GREATEST(i.total - ledger, 0)) >= 0.005
                                     OR ledger > i.total + 0.005))
            OR (i.docstatus = 2 AND ledger > 0)
        ORDER BY i.name LIMIT %s""", (int(limit),), as_dict=True)
    out = []
    for r in rows:
        if r.docstatus == 2:
            problem = f"cancelled, but {flt(r.ledger):,.2f} of payments are still submitted"
        elif flt(r.ledger) > flt(r.total) + 0.005:
            problem = f"payments of {flt(r.ledger):,.2f} exceed the total of {flt(r.total):,.2f}"
        else:
            problem = (f"stores paid {flt(r.paid_amount):,.2f} / outstanding {flt(r.outstanding):,.2f}; "
                       f"its payments come to {flt(r.ledger):,.2f}")
        out.append({"invoice": r.name, "tenant": r.tenant, "school": r.school_name, "problem": problem})
    return out


def check_ledger():
    """Scheduler (daily): find invoices that disagree with their payments without anyone opening them, and record
    them in the Error Log for the operator."""
    found = ledger_mismatches(limit=200)
    if found:
        frappe.log_error(title=f"Billing ledger: {len(found)} invoice(s) disagree with their payments",
                         message="\n".join(f"{m['invoice']} ({m['school'] or m['tenant']}): {m['problem']}" for m in found)
                         + "\n\nThe submitted payments are authoritative. Check each invoice before correcting it.")
        frappe.db.commit()
    return len(found)


@frappe.whitelist(methods=["GET"])
def subscription_billing(subscription):
    """The billing tile on a subscription: open invoice, last payment, totals."""
    sub = frappe.get_doc("SaaS Subscription", subscription)
    sub.check_permission("read")
    invoices = frappe.get_all("SaaS Invoice", filters={"subscription": subscription, "docstatus": 1},
                              fields=["name", "status", "total", "outstanding", "period_start", "period_end", "due_date"],
                              order_by="period_start desc", limit=5)
    last = frappe.get_all("SaaS Payment", filters={"invoice": ("in", [i.name for i in invoices] or [""]), "docstatus": 1},
                          fields=["name", "amount", "payment_date", "mode", "reference"], order_by="payment_date desc", limit=1)
    return {"invoices": invoices, "open": next((i for i in invoices if i.status in OPEN), None),
            "last_payment": last[0] if last else None, "outstanding": flt(sum(i.outstanding for i in invoices), 2),
            "currency": settings().currency, "next_period_start": str(next_period_start(sub)),
            "months": settings().billing_months}
