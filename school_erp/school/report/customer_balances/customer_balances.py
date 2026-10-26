# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt
"""What normal customers (not students) owe, by how overdue it is. Students' balances are in Fee Balances."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

from school_erp.api.report_utils import col

BUCKETS = (("current", "Not Yet Due", None), ("d30", "1-30 Days", 30), ("d60", "31-60 Days", 60), ("d90", "61-90 Days", 90), ("older", "Over 90 Days", None))


def execute(filters=None):
	f = frappe._dict(filters or {})
	as_on = getdate(f.as_on)
	cond, args = "", {"as_on": as_on}
	if f.customer_group:
		cond += " and c.customer_group = %(grp)s"; args["grp"] = f.customer_group
	invoices = frappe.db.sql(f"""
		select si.customer, c.customer_name, c.customer_group, si.due_date, si.posting_date, si.outstanding_amount
		from `tabSales Invoice` si join `tabCustomer` c on c.name = si.customer
		where si.docstatus = 1 and si.outstanding_amount != 0 and si.posting_date <= %(as_on)s
			and ifnull(si.student, '') = '' and ifnull(c.student, '') = '' {cond}""", args, as_dict=True)
	rows = {}
	for inv in invoices:
		r = rows.setdefault(inv.customer, frappe._dict(customer=inv.customer, customer_name=inv.customer_name,
							customer_group=inv.customer_group, invoices=0, outstanding=0, last_invoice=None,
							**{k: 0 for k, _l, _d in BUCKETS}))
		r.invoices += 1
		r.outstanding += flt(inv.outstanding_amount)
		r.last_invoice = max(filter(None, (r.last_invoice, inv.posting_date)))
		late = date_diff(as_on, inv.due_date or inv.posting_date)
		key = "current" if late <= 0 else "d30" if late <= 30 else "d60" if late <= 60 else "d90" if late <= 90 else "older"
		r[key] += flt(inv.outstanding_amount)
	columns = [col("customer", "Customer", "Link", 160, "Customer"), col("customer_name", "Name", "Data", 180),
			   col("customer_group", "Group", "Data", 130), col("invoices", "Open Invoices", "Int", 100),
			   col("outstanding", "Outstanding", "Currency", 120)]
	columns += [col(k, label, "Currency", 110) for k, label, _d in BUCKETS]
	columns.append(col("last_invoice", "Last Invoice", "Date", 100))
	data = sorted(rows.values(), key=lambda r: -r.outstanding)
	summary = [{"label": _("Owed by customers"), "value": sum(r.outstanding for r in data), "datatype": "Currency", "indicator": "Orange"},
			   {"label": _("Over 90 days"), "value": sum(r.older for r in data), "datatype": "Currency", "indicator": "Red"},
			   {"label": _("Customers owing"), "value": len(data), "datatype": "Int"}]
	return columns, data, None, None, summary
