# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import card, col, date_range
from school_erp.logic.pocket_money import CREDIT, balance_of, running_balance


@licensing.licensed("Pocket Money Transaction")
def execute(filters=None):
	"""One learner's pocket money in and out with a running balance (or every learner's movements when none is chosen)."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = ["docstatus = 1", "date(posting_datetime) between %(fd)s and %(td)s"], {"fd": fd, "td": td}
	opening = 0.0
	if f.student:
		cond.append("student = %(student)s")
		args["student"] = f.student
		before = frappe.get_all("Pocket Money Transaction", filters={"student": f.student, "docstatus": 1,
																	  "posting_datetime": ("<", fd)}, fields=["transaction_type", "amount"])
		opening = balance_of(before)
	data = frappe.db.sql(f"""select name, posting_datetime, student, student_name, transaction_type, amount, mode, reference,
			description, recorded_by from `tabPocket Money Transaction` where {" and ".join(cond)}
		order by posting_datetime, creation""", args, as_dict=True)
	rows = running_balance(data, opening) if f.student else [
		{**d, "credit": d.amount if d.transaction_type in CREDIT else 0, "debit": 0 if d.transaction_type in CREDIT else d.amount} for d in data]
	columns = [col("posting_datetime", "Date & Time", "Datetime", 150), col("name", "Transaction", "Link", 140, "Pocket Money Transaction")]
	if not f.student:
		columns.append(col("student_name", "Learner", "Data", 170))
	columns += [col("transaction_type", "Type", "Data", 110), col("description", "What For", "Data", 180),
				col("credit", "In", "Currency", 100), col("debit", "Out", "Currency", 100)]
	if f.student:
		columns.append(col("balance", "Balance", "Currency", 110))
	columns += [col("mode", "Paid By", "Data", 80), col("reference", "Reference", "Data", 120), col("recorded_by", "By", "Link", 140, "User")]
	money_in = sum(r["credit"] for r in rows)
	money_out = sum(r["debit"] for r in rows)
	summary = [card("Money in", money_in, "Currency", indicator="Green"), card("Money out", money_out, "Currency", indicator="Blue")]
	if f.student:
		summary = [card("Opening", opening, "Currency")] + summary + [card("Closing", rows[-1]["balance"] if rows else opening, "Currency")]
	return columns, rows, None, None, summary
