# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import nowdate

from school_erp import licensing
from school_erp.api.report_utils import card, col
from school_erp.logic.library import days_overdue, fine_for


@licensing.licensed("Library Loan")
def execute(filters=None):
	"""Books past their due date, who has them, and the fine so far."""
	from school_erp.api.library import library_settings

	f = frappe._dict(filters or {})
	s = library_settings()
	cond, args = ["status = 'On Loan'", "due_date < %(today)s"], {"today": nowdate()}
	if f.school_class:
		cond.append("school_class = %(cls)s")
		args["cls"] = f.school_class
	if f.borrower_type in ("Student", "Teacher"):
		cond.append("borrower_type = %(bt)s")
		args["bt"] = f.borrower_type
	rows = frappe.db.sql(f"""select name, borrower_type, student, teacher, borrower_name, school_class, book, book_title,
			accession_no, issue_date, due_date, last_reminder
		from `tabLibrary Loan` where {" and ".join(cond)} order by due_date""", args, as_dict=True)
	for r in rows:
		r["days_overdue"] = days_overdue(r.due_date, nowdate())
		r["fine_so_far"] = fine_for(r["days_overdue"], s.fine_per_day, s.fine_grace_days, s.max_fine)
	columns = [col("name", "Loan", "Link", 120, "Library Loan"), col("borrower_name", "Borrower", "Data", 170),
			   col("borrower_type", "Type", "Data", 80), col("school_class", "Class", "Link", 90, "School Class"),
			   col("book_title", "Book", "Data", 200), col("accession_no", "Copy", "Data", 100),
			   col("issue_date", "Issued", "Date", 95), col("due_date", "Due", "Date", 95),
			   col("days_overdue", "Days Overdue", "Int", 105), col("fine_so_far", "Fine So Far", "Currency", 110),
			   col("last_reminder", "Last Reminder", "Date", 110)]
	summary = [card("Overdue books", len(rows), indicator="Red" if rows else "Green"),
			   card("Borrowers", len({(r.student or r.teacher) for r in rows})),
			   card("Fines so far", sum(r["fine_so_far"] for r in rows), "Currency")]
	return columns, rows, None, None, summary
