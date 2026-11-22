"""Per month: money collected from schools, agents' commission, Stemic's costs by category, and what is left."""

import re

import frappe
from frappe import _
from frappe.utils import flt


def key(category):
	return re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")


def execute(filters=None):
	f = frappe._dict(filters or {})
	args = {"fd": f.from_date, "td": f.to_date}
	rows = {}

	def row(month):
		return rows.setdefault(month, frappe._dict(month=month, collected=0, commission=0, costs=0))

	for r in frappe.db.sql("""select date_format(payment_date, '%%Y-%%m') m, sum(amount) v from `tabSaaS Payment`
		where docstatus = 1 and payment_date between %(fd)s and %(td)s group by m""", args, as_dict=True):
		row(r.m).collected += flt(r.v)
	for r in frappe.db.sql("""select date_format(earned_on, '%%Y-%%m') m, sum(amount) v from `tabSaaS Commission`
		where status != 'Cancelled' and earned_on between %(fd)s and %(td)s group by m""", args, as_dict=True):
		row(r.m).commission += flt(r.v)
	categories = []
	for r in frappe.db.sql("""select date_format(posting_date, '%%Y-%%m') m, category, sum(amount) v from `tabStemic Expense`
		where docstatus = 1 and posting_date between %(fd)s and %(td)s group by m, category""", args, as_dict=True):
		k = key(r.category)
		if r.category not in categories:
			categories.append(r.category)
		row(r.m)[k] = flt(r.v)
		row(r.m).costs += flt(r.v)
	data = sorted(rows.values(), key=lambda r: r.month)
	for r in data:
		r.net = flt(r.collected - r.commission - r.costs, 2)
	cur = {"fieldtype": "Currency", "width": 130}
	columns = [{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 90},
			   {"fieldname": "collected", "label": _("Collected"), **cur}, {"fieldname": "commission", "label": _("Agent Commission"), **cur}]
	columns += [{"fieldname": key(c), "label": _(c), **cur} for c in sorted(categories)]
	columns += [{"fieldname": "costs", "label": _("Total Costs"), **cur}, {"fieldname": "net", "label": _("Left Over"), **cur}]
	chart = {"type": "bar", "data": {"labels": [r.month for r in data], "datasets": [
		{"name": _("Collected"), "values": [r.collected for r in data]},
		{"name": _("Costs + Commission"), "values": [flt(r.costs + r.commission) for r in data]}]}}
	total = lambda k: flt(sum(r[k] for r in data), 2)
	summary = [{"label": _("Collected"), "value": total("collected"), "datatype": "Currency", "indicator": "Green"},
			   {"label": _("Costs"), "value": total("costs"), "datatype": "Currency", "indicator": "Orange"},
			   {"label": _("Agent Commission"), "value": total("commission"), "datatype": "Currency", "indicator": "Blue"},
			   {"label": _("Left Over"), "value": total("net"), "datatype": "Currency",
				"indicator": "Green" if total("net") >= 0 else "Red"}]
	return columns, data, None, chart, summary
