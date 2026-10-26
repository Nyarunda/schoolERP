"""What each school owes, by how overdue it is."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

BUCKETS = (("current", "Not Yet Due"), ("d30", "1-30 Days"), ("d60", "31-60 Days"), ("d90", "61-90 Days"), ("older", "Over 90 Days"))


def execute(filters=None):
    f = frappe._dict(filters or {})
    as_on = getdate(f.as_on)
    cond = {"docstatus": 1, "status": ("in", ["Unpaid", "Partly Paid", "Overdue"]), "issue_date": ("<=", as_on)}
    if f.agent:
        cond["agent"] = f.agent
    rows = {}
    for inv in frappe.get_list("SaaS Invoice", filters=cond, fields=["name", "tenant", "school_name", "agent", "due_date", "outstanding"]):
        r = rows.setdefault(inv.tenant, frappe._dict(tenant=inv.tenant, school_name=inv.school_name, agent=inv.agent,
                                                      invoices=0, outstanding=0, **{k: 0 for k, _l in BUCKETS}))
        late = date_diff(as_on, inv.due_date)
        key = "current" if late <= 0 else "d30" if late <= 30 else "d60" if late <= 60 else "d90" if late <= 90 else "older"
        r[key] += flt(inv.outstanding)
        r.outstanding += flt(inv.outstanding)
        r.invoices += 1
    columns = [{"fieldname": "tenant", "label": _("School"), "fieldtype": "Link", "options": "SaaS Tenant", "width": 150},
               {"fieldname": "school_name", "label": _("Name"), "fieldtype": "Data", "width": 190},
               {"fieldname": "agent", "label": _("Agent"), "fieldtype": "Link", "options": "SaaS Agent", "width": 110},
               {"fieldname": "invoices", "label": _("Open Invoices"), "fieldtype": "Int", "width": 100},
               {"fieldname": "outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120}]
    columns += [{"fieldname": k, "label": _(l), "fieldtype": "Currency", "width": 110} for k, l in BUCKETS]
    data = sorted(rows.values(), key=lambda r: -r.outstanding)
    summary = [{"label": _("Owed by schools"), "value": sum(r.outstanding for r in data), "datatype": "Currency", "indicator": "Orange"},
               {"label": _("Over 90 days"), "value": sum(r.older for r in data), "datatype": "Currency", "indicator": "Red"},
               {"label": _("Schools owing"), "value": len(data), "datatype": "Int"}]
    return columns, data, None, None, summary
