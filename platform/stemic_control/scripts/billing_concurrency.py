"""Real concurrency checks for Stemic billing on a MariaDB-backed Frappe site.

Each client is a separate process with its own database connection, released together by a barrier. A 1.5 s pause is
injected inside the critical section (after the check, before the write) so the transactions overlap every time.
Every scenario runs with the PR's protections ("protected") and with the row locks removed ("control"), to show the
harness detects the race when nothing prevents it.

Run it on a disposable admin site. Its fixtures carry this run's own id (race-<run>-..., "Race Agent <run>",
"Race Plan <run>") and only those are removed at the end, so other data, or another run, is left alone:

    cd frappe-bench/sites
    ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost            # both modes
    ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost protected  # only with locks
    STEMIC_RACE_ONLY=s11,s12 ../env/bin/python ...                                                # only some scenarios

If a run is killed (its cleanup cannot run), remove what it left by its id, printed on the first line:

    ../env/bin/python ../apps/stemic_control/scripts/billing_concurrency.py admin.localhost --cleanup <run-id>

MariaDB 11.6+ turns innodb_snapshot_isolation ON: a transaction that would act on stale reads is aborted with error
1020 ("Record has changed since last read") instead. Races then fail safely before reaching the code under test, so
the control run cannot break. Set STEMIC_RACE_SNAPSHOT_ISOLATION=OFF (or ON) to choose it per connection; CI runs
both. The run's header says which applied; with it ON the control check is reported, not enforced.

Exit status (so a CI job or script can gate on it):
    0  every protected round consistent, no client crashed or hung, and every expected control race broke
    1  a protected round was inconsistent, or a client crashed or hung
    2  protected rounds were fine, but a control race no longer broke: the harness has stopped exercising it

Every "protected" round must print CONSISTENT. The "control" rounds are expected to break for the races the locks
exist for (double payment, two part-payments, two invoices, cancel vs pay, cancel invoice vs pay, and for eTIMS: two
preparations, cancel vs prepare, cancel vs queue; for provisioning: two workers on one job, two requests queueing one
school); if a control round stops breaking, the harness no longer exercises that race. The provisioning scenarios mock
Frappe's CLI: no site is ever created. The eTIMS scenarios switch on Stemic Tax Settings for the run and put the previous values back afterwards.

Results on MariaDB 10.11 (REPEATABLE READ), 27 Oct 2026: protected 33/33 consistent; control broke 8 of 11 scenarios.
With the tax invoice row read plainly (before the eTIMS fix) protected s9 broke 3/3 and s10 2/3.
"""

import multiprocessing as mp
import os
import sys
import time
import traceback

SITE = sys.argv[1] if len(sys.argv) > 1 else "admin.localhost"
RUN = None  # this run's id, set in main(); fixtures are named with it and only they are cleaned up
# Races the locks exist for: with the locks removed ("control") these must break, or the harness lost its teeth
EXPECT_CONTROL_BREAKS = {"s1_double_payment", "s1b_two_part_payments", "s3_double_invoice", "s4_cancel_vs_pay",
                         "s7_cancel_invoice_vs_pay", "s8_double_prepare", "s9_cancel_vs_prepare", "s10_cancel_vs_queue",
                         "s11_double_build", "s12_double_queue"}
ETIMS_ACTIONS = {"prepare", "queue", "cancel_taxed"}  # clients that get the pause after reading the tax invoice row
SITE_ACTIONS = {"build", "queue_site", "reject"}  # ... and after reading a provisioning job row
LOCKED = ("`tabSaaS Subscription`", "`tabSaaS Invoice`", "`tabSaaS Payment`", "`tabSaaS eTIMS Invoice`",
          "`tabSaaS Tenant`", "`tabSaaS Provisioning Job`")
PAUSE = 1.5
ROUNDS = 3


def set_snapshot_isolation(frappe):
    """Apply STEMIC_RACE_SNAPSHOT_ISOLATION to this connection (when the server has the variable); return the effect."""
    have = frappe.db.sql("SHOW VARIABLES LIKE 'innodb_snapshot_isolation'")
    if not have:
        return "n/a"
    wanted = (os.environ.get("STEMIC_RACE_SNAPSHOT_ISOLATION") or "").upper()
    if wanted in ("ON", "OFF"):
        frappe.db.sql(f"SET SESSION innodb_snapshot_isolation = {wanted}")
    return frappe.db.sql("SELECT @@SESSION.innodb_snapshot_isolation")[0][0] and "ON" or "OFF"


def connect():
    import frappe

    frappe.init(SITE, sites_path=".")
    frappe.connect()
    set_snapshot_isolation(frappe)
    frappe.set_user("Administrator")
    frappe.local.conf["stemic_platform_domain"] = "race.test"
    return frappe


def instrument(frappe, mode, action):
    """Widen the race window; in control mode also remove the row locks under test."""
    from stemic_control import billing

    real_sql = frappe.db.sql
    def sql(query, *a, **k):
        locked_read = isinstance(query, str) and "FOR UPDATE" in query and any(t in query for t in LOCKED)
        if mode == "control" and locked_read:
            # switch off only the billing and tax row locks under test (not Frappe's own naming-series lock)
            query = query.replace("FOR UPDATE", "")
        out = real_sql(query, *a, **k)
        if action in ETIMS_ACTIONS and locked_read and "`tabSaaS eTIMS Invoice`" in query:
            time.sleep(PAUSE)  # prepare, cancel guard, queue: read the tax invoice row ... then write
        if action in SITE_ACTIONS and locked_read and "`tabSaaS Provisioning Job`" in query:
            time.sleep(PAUSE)  # build: claim the job; queue / reject: look for an active job ... then write
        return out
    frappe.db.sql = sql
    if mode == "control":
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
        instrument(frappe, mode, action)
        from stemic_control import billing, etims

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
            elif action in ("cancel_invoice", "cancel_taxed"):
                frappe.get_doc("SaaS Invoice", args[0]).cancel()
                out = "invoice cancelled"
            elif action == "prepare":
                out = etims.prepare_from_saas_invoice(args[0])["name"]
            elif action in SITE_ACTIONS:
                out = site_action(frappe, action, args)
            elif action == "queue":
                # a provider is "configured" for this client only; nothing is enqueued or sent
                frappe.local.conf.update({"stemic_etims_live_enabled": 1, "stemic_etims_adapter": "stemic_control_integrations.race.submit"})
                frappe.enqueue = lambda *a, **k: None
                out = etims.queue_submission(args[0])["status"]
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


def site_action(frappe, action, args):
    """Provisioning with Frappe's CLI mocked: returns how many new-site commands this client would have run."""
    from frappe.utils import get_bench_path

    from stemic_control import api, onboarding, provisioner

    frappe.local.conf.update({"stemic_local_provisioner": 1, "stemic_provision_environment": "development",
                              "stemic_provision_allowed_benches": [get_bench_path()], "stemic_site_domain": "localhost",
                              "stemic_db_root_password": "not-used"})
    built = []
    provisioner._frappe_cli = lambda *a, **k: built.append(a[0]) or ("frappe\nerpnext\nschool_erp\n" if "list-apps" in a else "")
    provisioner._site_dir_exists = lambda site: False
    provisioner._database_exists = lambda name: False
    provisioner.enqueue = lambda job: None
    if action == "build":
        return f"{provisioner.run(args[0])}, new-site x{built.count('new-site')}"
    if action == "queue_site":
        return api.queue_provisioning(args[0], args[1])
    return onboarding.reject_tenant(args[0], "Rejected during the race")["status"]


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

    agent = frappe.db.get_value("SaaS Agent", {"agent_name": f"Race Agent {RUN}"}) or frappe.get_doc(
        {"doctype": "SaaS Agent", "agent_name": f"Race Agent {RUN}", "status": "Active", "commission_rate": 10}).insert().name
    plan = f"Race Plan {RUN}"
    if not frappe.db.exists("SaaS Plan", plan):
        frappe.get_doc({"doctype": "SaaS Plan", "plan_name": plan, "enabled": 1, "monthly_price": 1000, "modules": "[]"}).insert()
    tenant = api.register_tenant(f"Race School {tag}", f"race-{RUN}-{tag}-{frappe.generate_hash(length=4).lower()}", "race@race.test", agent)
    sub = frappe.get_doc({"doctype": "SaaS Subscription", "tenant": tenant, "plan": plan, "agent": agent,
                          "starts_on": add_days(nowdate(), -40), "ends_on": add_days(nowdate(), 5)}).insert().name
    frappe.db.commit()
    return tenant, sub


TAX_SELLER = {"enabled": 1, "seller_name": "Race Seller Ltd", "seller_pin": "P059999999Q", "branch_id": "00",
              "tax_treatment": "Standard Rated", "vat_rate": 16}
saved_tax_settings = None


def tax_seller(frappe):
    """Make Stemic a registered seller for the eTIMS scenarios, remembering what was there."""
    global saved_tax_settings
    doc = frappe.get_doc("Stemic Tax Settings")
    if saved_tax_settings is None:
        saved_tax_settings = {k: doc.get(k) for k in TAX_SELLER}
    doc.update(TAX_SELLER)
    doc.save()
    frappe.db.commit()


def taxed_invoice(frappe, tag, ready=False):
    from stemic_control import billing, etims

    tax_seller(frappe)
    _t, sub = fixture(frappe, tag)
    inv = billing._create_invoice(sub, 1); frappe.db.commit()
    if not ready:
        return inv, None
    tax = etims.prepare_from_saas_invoice(inv)["name"]
    etims.approve_invoice(tax); frappe.db.commit()
    return inv, tax


def tax_state(frappe, inv):
    frappe.db.rollback()
    rows = frappe.get_all("SaaS eTIMS Invoice", filters={"saas_invoice": inv}, fields=["name", "status"])
    return frappe.db.get_value("SaaS Invoice", inv, "docstatus"), rows


def eligible_school(frappe, tag):
    """An approved school with an approved internal subscription: one the provisioner would build."""
    from stemic_control import onboarding

    tenant, sub = fixture(frappe, tag)
    onboarding.submit_for_approval(tenant)
    onboarding.approve_tenant(tenant, "Race fixture")
    onboarding.grant_billing_exception(sub, onboarding.INTERNAL, "Race fixture school")
    frappe.db.commit()
    return tenant


def site_state(frappe, tenant):
    frappe.db.rollback()
    jobs = frappe.get_all("SaaS Provisioning Job", filters={"tenant": tenant}, fields=["name", "status"])
    return frappe.db.get_value("SaaS Tenant", tenant, "status"), jobs


def cleanup(frappe):
    """Remove this run's fixtures, and nothing else."""
    tenants = frappe.get_all("SaaS Tenant", filters={"name": ("like", f"race-{RUN}-%")}, pluck="name") or [""]
    invoices = frappe.get_all("SaaS Invoice", filters={"tenant": ("in", tenants)}, pluck="name") or [""]
    taxed = frappe.get_all("SaaS eTIMS Invoice", filters={"tenant": ("in", tenants)}, pluck="name") or [""]
    for dt, f in (("SaaS eTIMS Event", {"invoice": ("in", taxed)}), ("SaaS eTIMS Invoice", {"name": ("in", taxed)}),
                  ("SaaS Provisioning Job", {"tenant": ("in", tenants)}),
                  ("SaaS Commission", {"tenant": ("in", tenants)}), ("SaaS Payment", {"invoice": ("in", invoices)}),
                  ("SaaS Invoice", {"name": ("in", invoices)}), ("SaaS Subscription", {"tenant": ("in", tenants)}),
                  ("SaaS Domain", {"tenant": ("in", tenants)}), ("SaaS Tenant", {"name": ("in", tenants)}),
                  ("SaaS Agent", {"agent_name": f"Race Agent {RUN}"}), ("SaaS Plan", {"name": f"Race Plan {RUN}"})):
        frappe.db.delete(dt, f)
    if saved_tax_settings is not None:  # written directly: what was there before may not be a complete seller
        frappe.db.set_single_value("Stemic Tax Settings", saved_tax_settings)
        frappe.clear_document_cache("Stemic Tax Settings", "Stemic Tax Settings")
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


def s8_double_prepare(frappe, mode, tag):
    """Two clients prepare the tax invoice of the same SaaS Invoice: one record, and both get it back."""
    inv, _ = taxed_invoice(frappe, tag)
    res = run([("prepare", (inv,)), ("prepare", (inv,))], mode)
    _d, rows = tax_state(frappe, inv)
    # a refusal is only acceptable as MariaDB's own abort under snapshot isolation (error 1020), not a duplicate key
    refused = [r[1] for r in res if r[0] == "refused" and "1020" not in r[1]]
    same = len({r[1] for r in res if r[0] == "ok"}) <= 1
    return len(rows) == 1 and not refused and same, res, f"{len(rows)} tax record(s)"


def s9_cancel_vs_prepare(frappe, mode, tag):
    """Someone cancels a SaaS Invoice while its tax invoice is being prepared."""
    inv, _ = taxed_invoice(frappe, tag)
    res = run([("cancel_taxed", (inv,)), ("prepare", (inv,))], mode)
    docstatus, rows = tax_state(frappe, inv)
    live = [r for r in rows if r.status != "Withdrawn"]
    ok = not (docstatus == 2 and live)  # never a cancelled invoice whose tax invoice is still live
    return ok, res, f"invoice docstatus {docstatus}; tax invoice {', '.join(r.status for r in rows) or 'none'}"


def s10_cancel_vs_queue(frappe, mode, tag):
    """Someone cancels a SaaS Invoice while its reviewed tax invoice is queued for KRA."""
    inv, tax = taxed_invoice(frappe, tag, ready=True)
    res = run([("cancel_taxed", (inv,)), ("queue", (tax,))], mode)
    docstatus, rows = tax_state(frappe, inv)
    status = rows[0].status
    queued = frappe.db.exists("SaaS eTIMS Event", {"invoice": tax, "event_type": "Queued for provider"})
    # cancelled with a tax invoice on its way to KRA, or withdrawn after being queued: both lose track of a KRA filing
    ok = not (docstatus == 2 and status in ("Pending Submission", "Submitted")) and not (status == "Withdrawn" and queued)
    return ok, res, f"invoice docstatus {docstatus}; tax invoice {status}{' (after being queued)' if queued else ''}"


def s11_double_build(frappe, mode, tag):
    """Two workers pick up the same queued Create Site job: the site must be built once."""
    from unittest.mock import patch

    from stemic_control import api, provisioner

    tenant = eligible_school(frappe, tag)
    with patch.object(provisioner, "enqueue"):  # not to this site's real workers: the two clients below are the workers
        job = api.queue_provisioning(tenant, f"race-{RUN}-{tag}-key")
    frappe.db.commit()
    res = run([("build", (job,)), ("build", (job,))], mode)
    status, jobs = site_state(frappe, tenant)
    builds = sum(int(r[1].rsplit("x", 1)[1]) for r in res if r[0] == "ok")
    return builds == 1 and status == "Active", res, f"site built {builds} time(s); school {status}"


def s12_double_queue(frappe, mode, tag):
    """Two operators queue the same school with different request keys: one active job."""
    tenant = eligible_school(frappe, tag)
    res = run([("queue_site", (tenant, f"race-{RUN}-{tag}-a")), ("queue_site", (tenant, f"race-{RUN}-{tag}-b"))], mode)
    status, jobs = site_state(frappe, tenant)
    active = [j for j in jobs if j.status in ("Queued", "Running")]
    return len(active) == 1, res, f"{len(active)} active job(s); school {status}"


def s13_reject_vs_queue(frappe, mode, tag):
    """An operator rejects a school while another queues it: a rejected school must have no active job."""
    tenant = eligible_school(frappe, tag)
    res = run([("reject", (tenant,)), ("queue_site", (tenant, f"race-{RUN}-{tag}-q"))], mode)
    status, jobs = site_state(frappe, tenant)
    active = [j for j in jobs if j.status in ("Queued", "Running")]
    return not (status == "Rejected" and active), res, f"school {status}; {len(active)} active job(s)"


def main():
    global RUN
    import frappe

    frappe.init(SITE, sites_path="."); frappe.connect(); frappe.set_user("Administrator")
    if sys.argv[2:3] == ["--cleanup"]:
        RUN = (sys.argv[3:4] or [""])[0].strip().lower()
        if not RUN.isalnum():
            sys.exit("usage: billing_concurrency.py <site> --cleanup <run-id>")
        cleanup(frappe)
        print(f"removed the fixtures of run {RUN}")
        return
    frappe.local.conf["stemic_platform_domain"] = "race.test"
    RUN = frappe.generate_hash(length=6).lower()
    snapshot = set_snapshot_isolation(frappe)
    version = frappe.db.sql("SELECT VERSION()")[0][0]
    print(f"run {RUN} on {SITE} | {version} | innodb_snapshot_isolation {snapshot}", flush=True)
    stuck = []
    scenarios = [s1_double_payment, s1b_two_part_payments, s2_same_reference, s3_double_invoice, s4_cancel_vs_pay, s5_pay_vs_invoice,
                 s6_daily_vs_payment, s7_cancel_invoice_vs_pay, s8_double_prepare, s9_cancel_vs_prepare, s10_cancel_vs_queue,
                 s11_double_build, s12_double_queue, s13_reject_vs_queue]
    only = [x.strip() for x in (os.environ.get("STEMIC_RACE_ONLY") or "").split(",") if x.strip()]
    if only:  # e.g. STEMIC_RACE_ONLY=s11,s12 to run some scenarios while working on them (CI runs them all)
        scenarios = [sc for sc in scenarios if sc.__name__.split("_")[0] in only]
    summary = {}
    try:
        for mode in (sys.argv[2:] or ["protected", "control"]):
            for sc in scenarios:
                for n in range(ROUNDS):
                    tag = f"{sc.__name__.split('_')[0]}{mode[0]}{n}"
                    ok, res, detail = sc(frappe, mode, tag)
                    summary.setdefault((mode, sc.__name__), []).append(ok)
                    stuck += [f"{mode} {sc.__name__} round {n + 1}: {r[0]}" for r in res if r[0] in ("crash", "hung")]
                    print(f"[{mode:9s}] {sc.__name__:20s} round {n + 1}: {'CONSISTENT' if ok else 'BROKEN    '} | {detail} | "
                          + " ; ".join(f"{r[0]}" + (f" ({r[1]})" if r[0] != 'ok' else "") for r in res), flush=True)
    finally:
        cleanup(frappe)
    print("\nSUMMARY")
    for (mode, name), oks in summary.items():
        print(f"  {mode:9s} {name:20s} {sum(oks)}/{len(oks)} consistent")
    broken = [name for (mode, name), oks in summary.items() if mode == "protected" and not all(oks)]
    toothless = [name for (mode, name), oks in summary.items() if mode == "control" and name in EXPECT_CONTROL_BREAKS and all(oks)]
    if broken or stuck:
        print("\nFAIL: " + "; ".join([f"protected {b} inconsistent" for b in broken] + stuck))
        sys.exit(1)
    if toothless and snapshot == "ON":
        print("\nnote: snapshot isolation is ON, so races abort with error 1020 before the code under test and the control"
              " run cannot break; control is not enforced. Run with STEMIC_RACE_SNAPSHOT_ISOLATION=OFF to exercise the locks.")
        toothless = []
    if toothless:
        print("\nFAIL: the harness no longer exercises: " + ", ".join(toothless) + " (the control run stayed consistent)")
        sys.exit(2)
    print("\nPASS")


if __name__ == "__main__":
    main()
