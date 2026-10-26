"""Per month: what was invoiced, what was collected, and the commission earned on it."""

import frappe
from frappe import _
from frappe.utils import flt


def col(fieldname, label, fieldtype="Currency", width=130, options=None):
    return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **({"options": options} if options else {})}


def execute(filters=None):
    f = frappe._dict(filters or {})
    args = {"fd": f.from_date, "td": f.to_date, "plan": f.plan}
    plan = " and inv.plan = %(plan)s" if f.plan else ""
    rows = {}

    def row(month):
        return rows.setdefault(month, frappe._dict(month=month, invoiced=0, collected=0, commission=0, payments=0))

    for r in frappe.db.sql(f"""select date_format(issue_date, '%%Y-%%m') m, sum(total) v from `tabSaaS Invoice` inv
        where docstatus = 1 and issue_date between %(fd)s and %(td)s {plan} group by m""", args, as_dict=True):
        row(r.m).invoiced += flt(r.v)
    for r in frappe.db.sql(f"""select date_format(p.payment_date, '%%Y-%%m') m, sum(p.amount) v, count(*) n
        from `tabSaaS Payment` p join `tabSaaS Invoice` inv on inv.name = p.invoice
        where p.docstatus = 1 and p.payment_date between %(fd)s and %(td)s {plan} group by m""", args, as_dict=True):
        row(r.m).collected += flt(r.v)
        row(r.m).payments += r.n
    for r in frappe.db.sql(f"""select date_format(c.earned_on, '%%Y-%%m') m, sum(c.amount) v
        from `tabSaaS Commission` c join `tabSaaS Invoice` inv on inv.name = c.invoice
        where c.status != 'Cancelled' and c.earned_on between %(fd)s and %(td)s {plan} group by m""", args, as_dict=True):
        row(r.m).commission += flt(r.v)
    data = sorted(rows.values(), key=lambda r: r.month)
    for r in data:
        r.net = flt(r.collected - r.commission, 2)
    columns = [col("month", "Month", "Data", 100), col("invoiced", "Invoiced"), col("collected", "Collected"),
               col("payments", "Payments", "Int", 90), col("commission", "Agent Commission"), col("net", "Net of Commission")]
    chart = {"data": {"labels": [r.month for r in data], "datasets": [
        {"name": _("Invoiced"), "values": [r.invoiced for r in data]},
        {"name": _("Collected"), "values": [r.collected for r in data]}]},
        "type": "bar", "fieldtype": "Currency"} if data else None
    summary = [{"label": _("Invoiced"), "value": sum(r.invoiced for r in data), "datatype": "Currency"},
               {"label": _("Collected"), "value": sum(r.collected for r in data), "datatype": "Currency", "indicator": "Green"},
               {"label": _("Commission"), "value": sum(r.commission for r in data), "datatype": "Currency", "indicator": "Orange"}]
    return columns, data, None, chart, summary
