"""Figures for the Stemic Control workspaces that a Number Card cannot count by itself."""

import frappe


@frappe.whitelist()
def monthly_recurring_revenue(filters=None):
    """Sum of the monthly plan price of every Active subscription."""
    if not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)
    total = frappe.db.sql(
        """select coalesce(sum(p.monthly_price), 0)
        from `tabSaaS Subscription` s join `tabSaaS Plan` p on p.name = s.plan
        where s.status = 'Active'"""
    )[0][0]
    return {"value": total, "fieldtype": "Currency"}


# ----------------------------------------------------------------------------- the Overview page
PIPELINE = [  # (label, statuses, what it means)
    ("Registered", ["Draft"], "Saved, not sent for approval"),
    ("Awaiting approval", ["Pending Approval"], "A platform admin must approve or reject"),
    ("Approved", ["Approved"], "Ready to build the site"),
    ("Building site", ["Pending", "Provisioning"], "Queued or being created"),
    ("Live", ["Active"], "Using their site"),
]
LIVE_SUBS = ("Trial", "Active", "Past Due", "Grace")


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw("Platform administrator access required", frappe.PermissionError)


def _months(n=12):
    """The first day of each of the last n months, oldest first, and their labels (Jan 26)."""
    from frappe.utils import add_months, get_first_day, getdate, nowdate

    first = get_first_day(getdate(nowdate()))
    days = [add_months(first, -i) for i in range(n - 1, -1, -1)]
    return days, [d.strftime("%b %y") for d in days]


def _by_month(sql, days, args=None):
    rows = {str(k): float(v or 0) for k, v in frappe.db.sql(sql, {"since": days[0], **(args or {})})}
    return [rows.get(d.strftime("%Y-%m"), 0) for d in days]


@frappe.whitelist(methods=["GET"])
def overview():
    """Everything the Stemic Overview page shows on its first tab, in one call: money, the onboarding pipeline, the
    last 12 months of collections and new schools, renewals and trials coming up, plans, agents and setup."""
    _admin()
    from frappe.utils import add_days, get_first_day, getdate, nowdate

    from stemic_control.billing import OPEN, settings

    today = getdate(nowdate())
    month_start = get_first_day(today)
    sql = frappe.db.sql

    mrr = sql("""select coalesce(sum(p.monthly_price), 0) from `tabSaaS Subscription` s
                 join `tabSaaS Plan` p on p.name = s.plan where s.status = 'Active'""")[0][0]
    collected = sql("""select coalesce(sum(amount), 0) from `tabSaaS Payment`
                       where docstatus = 1 and payment_date >= %s""", month_start)[0][0]
    collected_last = sql("""select coalesce(sum(amount), 0) from `tabSaaS Payment` where docstatus = 1
                            and payment_date >= %s and payment_date < %s""",
                         (frappe.utils.add_months(month_start, -1), month_start))[0][0]
    owed, overdue = sql("""select coalesce(sum(outstanding), 0), coalesce(sum(if(status = 'Overdue', outstanding, 0)), 0)
                           from `tabSaaS Invoice` where docstatus = 1 and status in %s""", (OPEN,))[0]
    commission_due = sql("select coalesce(sum(amount), 0) from `tabSaaS Commission` where status = 'Due'")[0][0]

    by_status = dict(sql("select status, count(*) from `tabSaaS Tenant` group by status"))
    pipeline = [{"label": label, "statuses": statuses, "hint": hint, "count": sum(by_status.get(s, 0) for s in statuses)}
                for label, statuses, hint in PIPELINE]
    stuck = [{"label": s, "count": by_status.get(s, 0)} for s in ("Failed", "Suspended", "Rejected") if by_status.get(s)]

    days, labels = _months()
    collections = _by_month("""select date_format(payment_date, '%%Y-%%m'), sum(amount) from `tabSaaS Payment`
                               where docstatus = 1 and payment_date >= %(since)s group by 1""", days)
    invoiced = _by_month("""select date_format(issue_date, '%%Y-%%m'), sum(total) from `tabSaaS Invoice`
                            where docstatus = 1 and issue_date >= %(since)s group by 1""", days)
    new_schools = _by_month("""select date_format(creation, '%%Y-%%m'), count(*) from `tabSaaS Tenant`
                               where creation >= %(since)s group by 1""", days)
    went_live = _by_month("""select date_format(j.modified, '%%Y-%%m'), count(distinct j.tenant) from `tabSaaS Provisioning Job` j
                             where j.action = 'Create Site' and j.status = 'Succeeded' and j.modified >= %(since)s group by 1""", days)

    horizon = add_days(today, 30)
    renewals = sql("""select s.name, s.tenant, t.school_name, s.plan, s.status, s.ends_on, s.billing_exception,
                             p.monthly_price,
                             (select i.name from `tabSaaS Invoice` i where i.subscription = s.name and i.docstatus = 1
                                and i.status in %(open)s order by i.creation desc limit 1) as invoice,
                             (select i.outstanding from `tabSaaS Invoice` i where i.subscription = s.name and i.docstatus = 1
                                and i.status in %(open)s order by i.creation desc limit 1) as outstanding
                      from `tabSaaS Subscription` s
                      left join `tabSaaS Tenant` t on t.name = s.tenant
                      left join `tabSaaS Plan` p on p.name = s.plan
                      where s.status in %(live)s and s.ends_on between %(today)s and %(horizon)s
                        and ifnull(s.billing_exception, '') != 'Internal / Demo'
                      order by s.ends_on asc limit 12""",
                   {"open": OPEN, "live": LIVE_SUBS, "today": today, "horizon": horizon}, as_dict=True)
    for r in renewals:
        r.days_left = (getdate(r.ends_on) - today).days
        r.kind = "Trial ends" if r.status == "Trial" else "Renewal"

    plans = sql("""select p.name, p.monthly_price, sum(s.status = 'Active') as active, sum(s.status = 'Trial') as trial,
                          sum(s.status in ('Past Due', 'Grace')) as late
                   from `tabSaaS Plan` p left join `tabSaaS Subscription` s on s.plan = p.name
                   where p.enabled = 1 group by p.name, p.monthly_price order by p.monthly_price""", as_dict=True)
    for p in plans:
        p.active, p.trial, p.late = int(p.active or 0), int(p.trial or 0), int(p.late or 0)
        p.mrr = float(p.monthly_price or 0) * p.active

    year_start = frappe.utils.get_year_start(today)
    agents = sql("""select a.name, a.agent_name, a.commission_rate,
                           (select count(*) from `tabSaaS Tenant` t where t.agent = a.name) as schools,
                           (select count(*) from `tabSaaS Tenant` t where t.agent = a.name and t.status = 'Active') as live,
                           (select coalesce(sum(pay.amount), 0) from `tabSaaS Payment` pay join `tabSaaS Tenant` t
                              on t.name = pay.tenant where t.agent = a.name and pay.docstatus = 1
                              and pay.payment_date >= %(year)s) as collected,
                           (select coalesce(sum(c.amount), 0) from `tabSaaS Commission` c
                              where c.agent = a.name and c.status = 'Due') as due
                    from `tabSaaS Agent` a where a.status = 'Active'
                    order by collected desc, schools desc limit 8""", {"year": year_start}, as_dict=True)

    try:
        from stemic_control import setup_check

        items = setup_check.status()["items"]
        todo = [i for i in items if i["ok"] is False]
        setup = {"total": sum(1 for i in items if i["ok"] is not None), "ready": sum(1 for i in items if i["ok"] is True),
                 "todo": todo[:6], "more": max(0, len(todo) - 6)}
    except Exception:
        frappe.log_error(title="Overview: setup check failed")
        setup = None

    return {
        "currency": settings().currency,
        "money": {"mrr": mrr, "arr": mrr * 12, "collected": collected, "collected_last": collected_last, "owed": owed,
                  "overdue": overdue, "commission_due": commission_due,
                  "active_subscriptions": frappe.db.count("SaaS Subscription", {"status": "Active"}),
                  "trials": frappe.db.count("SaaS Subscription", {"status": "Trial"}),
                  "renewals_30": len(renewals)},
        "schools": {"total": sum(by_status.values()), "live": by_status.get("Active", 0)},
        "pipeline": pipeline, "stuck": stuck,
        "months": labels, "collections": collections, "invoiced": invoiced, "new_schools": new_schools,
        "went_live": went_live,
        "renewals": renewals, "plans": plans, "agents": agents, "setup": setup,
    }
