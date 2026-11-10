# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_first_day, nowdate

from school_erp import licensing
from school_erp.api.report_utils import card, col


@licensing.licensed("Pocket Money Account")
def execute(filters=None):
	"""What the school holds for each learner (a liability), and this month's money in and out."""
	f = frappe._dict(filters or {})
	cond, args = [], {"month": get_first_day(nowdate())}
	if f.school_class:
		cond.append("a.school_class = %(cls)s")
		args["cls"] = f.school_class
	if f.frozen_only:
		cond.append("a.is_frozen = 1")
	rows = frappe.db.sql(f"""
		select a.name as account, a.student, a.student_name, a.school_class, a.balance, a.daily_limit, a.is_frozen,
			a.last_transaction,
			(select ifnull(sum(t.amount), 0) from `tabPocket Money Transaction` t where t.student = a.student and t.docstatus = 1
				and t.transaction_type in ('Deposit', 'Refund', 'Adjustment In') and t.posting_datetime >= %(month)s) as in_month,
			(select ifnull(sum(t.amount), 0) from `tabPocket Money Transaction` t where t.student = a.student and t.docstatus = 1
				and t.transaction_type in ('Purchase', 'Withdrawal', 'Adjustment Out') and t.posting_datetime >= %(month)s) as out_month
		from `tabPocket Money Account` a {"where " + " and ".join(cond) if cond else ""}
		order by a.school_class, a.student_name""", args, as_dict=True)
	columns = [col("student", "Learner", "Link", 120, "Student"), col("student_name", "Name", "Data", 180),
			   col("school_class", "Class", "Link", 100, "School Class"), col("balance", "Balance", "Currency", 120),
			   col("in_month", "In This Month", "Currency", 120), col("out_month", "Spent This Month", "Currency", 130),
			   col("daily_limit", "Daily Limit", "Currency", 105), col("is_frozen", "Frozen", "Check", 70),
			   col("last_transaction", "Last Transaction", "Datetime", 150)]
	held = sum(r.balance or 0 for r in rows)
	summary = [card("Held for learners", held, "Currency", indicator="Blue"), card("Accounts", len(rows)),
			   card("Spent this month", sum(r.out_month or 0 for r in rows), "Currency"),
			   card("Zero balance", sum(1 for r in rows if (r.balance or 0) <= 0), indicator="Orange")]
	return columns, rows, None, None, summary
