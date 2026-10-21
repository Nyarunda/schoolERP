# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters), None, chart(filters)


def columns():
	return [
		{"fieldname": "student", "label": _("Student ID"), "fieldtype": "Link", "options": "Student", "width": 130},
		{"fieldname": "student_name", "label": _("Name"), "fieldtype": "Data", "width": 190},
		{"fieldname": "school_class", "label": _("Class"), "fieldtype": "Link", "options": "School Class", "width": 100},
		{"fieldname": "stream", "label": _("Stream"), "fieldtype": "Link", "options": "Stream", "width": 120},
		{"fieldname": "guardian", "label": _("Parent"), "fieldtype": "Data", "width": 150},
		{"fieldname": "phone", "label": _("Phone"), "fieldtype": "Data", "width": 120},
		{"fieldname": "billed", "label": _("Billed"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 130},
	]


def data(filters):
	conds, args = ["1=1"], {}
	for f in ("school_class", "stream", "status"):
		if filters.get(f):
			conds.append(f"s.{f} = %({f})s")
			args[f] = filters[f]
	term_cond = ""
	if filters.get("school_term"):
		term_cond = "and si.school_term = %(school_term)s"
		args["school_term"] = filters.school_term

	rows = frappe.db.sql(
		f"""
		select s.name as student, s.student_name, s.school_class, s.stream,
			s.primary_guardian as guardian, s.primary_phone as phone,
			coalesce((select sum(si.grand_total) from `tabSales Invoice` si
				where si.customer = s.customer and si.docstatus = 1 and si.is_return = 0 {term_cond}), 0) as billed,
			coalesce((select sum(gl.debit - gl.credit) from `tabGL Entry` gl
				where gl.party_type = 'Customer' and gl.party = s.customer and gl.is_cancelled = 0), 0) as balance
		from `tabStudent` s
		where {" and ".join(conds)}
		order by s.school_class, s.stream, s.student_name
		""",
		args,
		as_dict=True,
	)
	if filters.get("school_term"):
		outstanding = dict(
			frappe.db.sql(
				"""select si.customer, sum(si.outstanding_amount) from `tabSales Invoice` si
				where si.docstatus = 1 and si.school_term = %s group by si.customer""",
				filters.school_term,
			)
		)
		for r in rows:
			r["balance"] = flt(outstanding.get(r["student"]))  # customer id == student id
	for r in rows:
		r["paid"] = flt(r["billed"]) - flt(r["balance"])
	min_bal = flt(filters.get("min_balance"))
	if filters.get("only_with_balance") or min_bal:
		rows = [r for r in rows if flt(r["balance"]) >= max(min_bal, 0.01)]
	return rows


def chart(filters):
	rows = data(filters)
	by_class = {}
	for r in rows:
		by_class[r["school_class"] or "-"] = by_class.get(r["school_class"] or "-", 0) + max(flt(r["balance"]), 0)
	if not by_class:
		return None
	return {
		"data": {"labels": list(by_class), "datasets": [{"name": _("Balance owed"), "values": list(by_class.values())}]},
		"type": "bar",
		"fieldtype": "Currency",
	}
