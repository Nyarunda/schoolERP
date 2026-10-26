"""Each commission earned: school, payment, rate, amount and whether it has been paid out. Agents see only theirs."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    f = frappe._dict(filters or {})
    cond = {"earned_on": ("between", [f.from_date, f.to_date]), "status": ("!=", "Cancelled")}
    if f.agent:
        cond["agent"] = f.agent
    if f.status:
        cond["status"] = f.status
    data = frappe.get_list("SaaS Commission", filters=cond, order_by="earned_on",  # get_list: agents see only their own
                           fields=["earned_on", "agent", "school_name", "invoice", "payment", "base_amount", "rate", "amount",
                                   "status", "paid_on", "paid_reference"])
    columns = [
        {"fieldname": "earned_on", "label": _("Earned"), "fieldtype": "Date", "width": 95},
        {"fieldname": "agent", "label": _("Agent"), "fieldtype": "Link", "options": "SaaS Agent", "width": 110},
        {"fieldname": "school_name", "label": _("School"), "fieldtype": "Data", "width": 180},
        {"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "SaaS Invoice", "width": 130},
        {"fieldname": "base_amount", "label": _("Payment"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "rate", "label": _("Rate %"), "fieldtype": "Percent", "width": 70},
        {"fieldname": "amount", "label": _("Commission"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 70},
        {"fieldname": "paid_on", "label": _("Paid On"), "fieldtype": "Date", "width": 95},
        {"fieldname": "paid_reference", "label": _("Payout Ref"), "fieldtype": "Data", "width": 120},
    ]
    summary = [{"label": _("Earned"), "value": sum(flt(r.amount) for r in data), "datatype": "Currency"},
               {"label": _("Paid out"), "value": sum(flt(r.amount) for r in data if r.status == "Paid"), "datatype": "Currency", "indicator": "Green"},
               {"label": _("Due"), "value": sum(flt(r.amount) for r in data if r.status == "Due"), "datatype": "Currency", "indicator": "Orange"}]
    return columns, data, None, None, summary
