"""Real concurrency checks for Stemic billing on a MariaDB-backed Frappe site.

Each client is a separate process with its own database connection, released together by a barrier. A 1.5 s pause is
injected inside the critical section (after the check, before the write) so the transactions overlap every time.
Every scenario runs with the PR's protections ("protected") and with the row locks removed ("control"), to show the
harness detects the race when nothing prevents it.

Run it on a disposable admin site (it commits fixtures named race-*, and removes them at the end):

    cd frappe-bench/sites
    ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost            # both modes
    ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost protected  # only with locks

Every "protected" round must print CONSISTENT. The "control" rounds are expected to break for the races the locks
exist for (double payment, two part-payments, two invoices, cancel vs pay, cancel invoice vs pay); if a control round
stops breaking, the harness no longer exercises that race.

Results on MariaDB 10.11 (REPEATABLE READ), 26 Oct 2026: protected 24/24 consistent; control broke 5 of 8 scenarios.
"""

import multiprocessing as mp
import sys
import time
import traceback

SITE = sys.argv[1] if len(sys.argv) > 1 else "admin.localhost"
PAUSE = 1.5
ROUNDS = 3


def connect():
    import frappe

    frappe.init(SITE, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.local.conf["stemic_platform_domain"] = "race.test"
    return frappe


def instrument(frappe, mode):
    """Widen the race window; in control mode also remove the row locks under test."""
    from stemic_control import billing

    real_sql = frappe.db.sql
    if mode == "control":
        def sql(query, *a, **k):
            # switch off only the billing row locks under test (not Frappe's own naming-series lock)
            if isinstance(query, str) and "FOR UPDATE" in query and ("`tabSaaS Subscription`" in query or "`tabSaaS Invoice`" in query or "`tabSaaS Payment`" in query):
                query = query.replace("FOR UPDATE", "")
            return real_sql(query, *a, **k)
        frappe.db.sql = sql
        # no lock: report the status from an ordinary (snapshot) read, as the code did before the fix
        billing.lock_invoice = lambda invoice: frappe.db.get_value("SaaS Invoice", invoice, "docstatus")

    real_open = billing.open_invoice
    def slow_open(subscription):  # create_invoice: check for an open invoice ... then insert
        out = real_open(subscription)
        time.sleep(PAUSE)
        return out
    billing.open_invoice = slow_open

    real_submit_check = billing.validate_payment_for_submit
    def slow_submit_check(doc):  # payment submit: lock, read the live balance ... then post
        real_submit_check(doc)
        time.sleep(PAUSE)
    billing.validate_payment_for_submit = slow_submit_check


def client(action, args, mode, barrier, results, idx):
    try:
        frappe = connect()
        instrument(frappe, mode)
        from stemic_control import billing

        barrier.wait(timeout=60)
        try:
            if action == "pay":
                invoice, amount, ref = args
                out = billing.record_payment(invoice, amount, "M-Pesa", ref)["payment"]
            elif action == "invoice":
                out = billing._create_invoice(args[0], 1)
            elif action == "cancel":
                frappe.get_doc("SaaS Payment", args[0]).cancel()
                out = "cancelled"
            elif action == "cancel_invoice":
                frappe.get_doc("SaaS Invoice", args[0]).cancel()
                out = "invoice cancelled"
            elif action == "daily":
                from unittest.mock import patch

                with patch.object(frappe.db, "commit"):
                    billing.daily()
                out = "daily"
            frappe.db.commit()
            results[idx] = ("ok", out)
        except Exception as e:
            frappe.db.rollback()
            results[idx] = ("refused", f"{type(e).__name__}: {str(e)[:90]}")
    except Exception:
        results[idx] = ("crash", traceback.format_exc()[-300:])


def run(actions, mode):
    ctx = mp.get_context("spawn")
    barrier, manager = ctx.Barrier(len(actions)), ctx.Manager()
    results = manager.dict()
    procs = [ctx.Process(target=client, args=(a, args, mode, barrier, results, i)) for i, (a, args) in enumerate(actions)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=120)
    return [results.get(i, ("hung", "")) for i in range(len(actions))]


# ----------------------------------------------------------------------------- fixtures (committed, removed at the end)
def fixture(frappe, tag):
    from frappe.utils import add_days, nowdate

    from stemic_control import api

    agent = frappe.db.get_value("SaaS Agent", {"agent_name": "Race Agent"}) or frappe.get_doc(
        {"doctype": "SaaS Agent", "agent_name": "Race Agent", "status": "Active", "commission_rate": 10}).insert().name
    plan = "Race Plan"
    if not frappe.db.exists("SaaS Plan", plan):
        frappe.get_doc({"doctype": "SaaS Plan", "plan_name": plan, "enabled": 1, "monthly_price": 1000, "modules": "[]"}).insert()
    tenant = api.register_tenant(f"Race School {tag}", f"race-{tag}-{frappe.generate_hash(length=4).lower()}", "race@race.test", agent)
    sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": tenant, "plan": plan, "agent": agent,
                          "starts_on": add_days(nowdate(), -40), "ends_on": add_days(nowdate(), 5)}).insert().name
    frappe.db.commit()
    return tenant, sub


def cleanup(frappe):
    tenants = frappe.get_all("SaaS Tenant", filters={"name": ("like", "race-%")}, pluck="name") or [""]
    invoices = frappe.get_all("SaaS Invoice", filters={"tenant": ("in", tenants)}, pluck="name") or [""]
    for dt, f in (("SaaS Commission", {"tenant": ("in", tenants)}), ("SaaS Payment", {"invoice": ("in", invoices)}),
                  ("SaaS Invoice", {"name": ("in", invoices)}), ("SaaS Subscription", {"tenant": ("in", tenants)}),
                  ("SaaS Domain", {"tenant": ("in", tenants)}), ("SaaS Tenant", {"name": ("in", tenants)}),
                  ("SaaS Agent", {"agent_name": "Race Agent"}), ("SaaS Plan", {"name": "Race Plan"})):
        frappe.db.delete(dt, f)
    frappe.db.commit()


def state(frappe, sub):
    from frappe.utils import flt

    frappe.db.rollback()  # a fresh snapshot, so the checker sees what the clients committed
    invs = frappe.get_all("SaaS Invoice", filters={"subscription": sub, "docstatus": 1},
                          fields=["name", "total", "paid_amount", "outstanding", "status"])
    paid = {i.name: flt(frappe.db.sql("select coalesce(sum(amount),0) from `tabSaaS Payment` where invoice=%s and docstatus=1", i.name)[0][0])
            for i in invs}
    coms = frappe.db.count("SaaS Commission", {"invoice": ("in", [i.name for i in invs] or [""]), "status": ("!=", "Cancelled")})
    return invs, paid, coms


# ----------------------------------------------------------------------------- scenarios
def s1_double_payment(frappe, mode, tag):
    """Two clients each pay the invoice's full balance at the same moment."""
    from stemic_control import billing

    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1); frappe.db.commit()
    total = frappe.db.get_value("SaaS Invoice", inv, "total")
    res = run([("pay", (inv, total, f"QA{tag}1")), ("pay", (inv, total, f"QA{tag}2"))], mode)
    invs, paid, coms = state(frappe, sub)
    ok = paid[inv] <= total + 0.005 and coms == sum(r[0] == "ok" for r in res)
    return ok, res, f"paid {paid[inv]:.0f} of {total:.0f}; {coms} commission(s)"


def s1b_two_part_payments(frappe, mode, tag):
    """Two clients each pay 600 against a 1,000 invoice at the same moment: together they would overpay."""
    from stemic_control import billing

    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1); frappe.db.commit()
    res = run([("pay", (inv, 600, f"QP{tag}1")), ("pay", (inv, 600, f"QP{tag}2"))], mode)
    invs, paid, coms = state(frappe, sub)
    stored = next(i for i in invs if i.name == inv)
    ok = paid[inv] <= stored.total + 0.005 and abs(stored.paid_amount - paid[inv]) < 0.005
    return ok, res, f"ledger paid {paid[inv]:.0f} of {stored.total:.0f}; invoice says paid {stored.paid_amount:.0f}, {stored.status}"


def s2_same_reference(frappe, mode, tag):
    """Two clients record the same M-Pesa code against two different schools' invoices."""
    from stemic_control import billing

    _a, sub_a = fixture(frappe, tag + "a")
    _b, sub_b = fixture(frappe, tag + "b")
    inv_a = billing._create_invoice(sub_a, 1); inv_b = billing._create_invoice(sub_b, 1); frappe.db.commit()
    ref = f"QSAME{tag}"
    res = run([("pay", (inv_a, 500, ref)), ("pay", (inv_b, 500, ref))], mode)
    used = frappe.db.count("SaaS Payment", {"reference": ref, "docstatus": 1})
    return used <= 1, res, f"reference used by {used} submitted payment(s)"


def s3_double_invoice(frappe, mode, tag):
    """Two clients raise the next invoice for the same subscription."""
    _t, sub = fixture(frappe, tag)
    res = run([("invoice", (sub,)), ("invoice", (sub,))], mode)
    invs, _p, _c = state(frappe, sub)
    open_ = [i for i in invs if i.status in ("Unpaid", "Partly Paid", "Overdue")]
    return len(open_) <= 1, res, f"{len(open_)} open invoice(s)"


def s4_cancel_vs_pay(frappe, mode, tag):
    """One client cancels a part-payment while another pays the rest."""
    from stemic_control import billing

    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1); frappe.db.commit()
    first = billing.record_payment(inv, 400, "M-Pesa", f"QC{tag}1")["payment"]; frappe.db.commit()
    res = run([("cancel", (first,)), ("pay", (inv, 600, f"QC{tag}2"))], mode)
    frappe.db.rollback()
    invs, paid, _c = state(frappe, sub)
    inv_doc = next(i for i in invs if i.name == inv)
    ok = abs(inv_doc.paid_amount - paid[inv]) < 0.005 and abs(inv_doc.outstanding - (inv_doc.total - paid[inv])) < 0.005
    return ok, res, f"stored paid {inv_doc.paid_amount:.0f} vs ledger {paid[inv]:.0f}; outstanding {inv_doc.outstanding:.0f}"


def s5_pay_vs_invoice(frappe, mode, tag):
    """One client pays the open invoice while another tries to raise the next one (lock-order / deadlock probe)."""
    from stemic_control import billing

    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1); frappe.db.commit()
    total = frappe.db.get_value("SaaS Invoice", inv, "total")
    start = time.time()
    res = run([("pay", (inv, total, f"QD{tag}")), ("invoice", (sub,))], mode)
    invs, paid, _c = state(frappe, sub)
    hung = any(r[0] in ("hung", "crash") for r in res)
    deadlock = any("Deadlock" in r[1] or "QueryDeadlock" in r[1] for r in res)
    ok = not hung and not deadlock and paid[inv] == total
    return ok, res, f"{len(invs)} invoice(s); took {time.time() - start:.1f}s{'; DEADLOCK' if deadlock else ''}"


def s6_daily_vs_payment(frappe, mode, tag):
    """The daily job marks an invoice overdue while the school pays it in full."""
    from frappe.utils import add_days, nowdate

    from stemic_control import billing

    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1)
    frappe.db.set_value("SaaS Invoice", inv, {"issue_date": add_days(nowdate(), -20), "due_date": add_days(nowdate(), -1)})
    frappe.db.commit()
    total = frappe.db.get_value("SaaS Invoice", inv, "total")
    res = run([("pay", (inv, total, f"QE{tag}")), ("daily", ())], mode)
    invs, paid, _c = state(frappe, sub)
    stored = next(i for i in invs if i.name == inv)
    want = "Paid" if paid[inv] >= total else "Overdue"
    return stored.status == want and abs(stored.paid_amount - paid[inv]) < 0.005, res, f"ledger {paid[inv]:.0f}, invoice {stored.status}"


def s7_cancel_invoice_vs_pay(frappe, mode, tag):
    """Someone cancels an invoice while a payment against it is being recorded."""
    from stemic_control import billing

    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1); frappe.db.commit()
    res = run([("cancel_invoice", (inv,)), ("pay", (inv, 500, f"QF{tag}"))], mode)
    frappe.db.rollback()
    docstatus = frappe.db.get_value("SaaS Invoice", inv, "docstatus")
    payments = frappe.db.count("SaaS Payment", {"invoice": inv, "docstatus": 1})
    ok = not (docstatus == 2 and payments)  # never a cancelled invoice with a live payment
    return ok, res, f"invoice docstatus {docstatus}, {payments} live payment(s)"


def main():
    import frappe

    frappe.init(SITE, sites_path="."); frappe.connect(); frappe.set_user("Administrator")
    frappe.local.conf["stemic_platform_domain"] = "race.test"
    cleanup(frappe)
    scenarios = [s1_double_payment, s1b_two_part_payments, s2_same_reference, s3_double_invoice, s4_cancel_vs_pay, s5_pay_vs_invoice,
                 s6_daily_vs_payment, s7_cancel_invoice_vs_pay]
    summary = {}
    try:
        for mode in (sys.argv[2:] or ["protected", "control"]):
            for sc in scenarios:
                for n in range(ROUNDS):
                    tag = f"{sc.__name__.split('_')[0]}{mode[0]}{n}"
                    ok, res, detail = sc(frappe, mode, tag)
                    summary.setdefault((mode, sc.__name__), []).append(ok)
                    print(f"[{mode:9s}] {sc.__name__:20s} round {n + 1}: {'CONSISTENT' if ok else 'BROKEN    '} | {detail} | "
                          + " ; ".join(f"{r[0]}" + (f" ({r[1]})" if r[0] != 'ok' else "") for r in res), flush=True)
    finally:
        cleanup(frappe)
    print("\nSUMMARY")
    for (mode, name), oks in summary.items():
        print(f"  {mode:9s} {name:20s} {sum(oks)}/{len(oks)} consistent")


if __name__ == "__main__":
    main()
