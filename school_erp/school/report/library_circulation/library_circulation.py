# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col, date_range, top


@licensing.licensed("Library Loan")
def execute(filters=None):
	"""What was borrowed in a period: by book (most popular first), category or class."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	group = f.group_by if f.group_by in ("Book", "Category", "Class") else "Book"
	key = {"Book": "l.book", "Category": "b.category", "Class": "l.school_class"}[group]
	rows = frappe.db.sql(f"""select {key} as grp, max(l.book_title) as title, count(*) as loans,
			sum(l.status = 'On Loan') as still_out, sum(l.status = 'Lost') as lost, sum(l.days_overdue > 0) as returned_late,
			sum(l.fine_amount) as fines, count(distinct ifnull(l.student, l.teacher)) as borrowers
		from `tabLibrary Loan` l join `tabLibrary Book` b on b.name = l.book
		where l.issue_date between %(fd)s and %(td)s group by {key} order by loans desc""", {"fd": fd, "td": td}, as_dict=True)
	link = {"Book": "Library Book", "Class": "School Class"}.get(group)
	columns = [col("grp", group, "Link" if link else "Data", 140, link)]
	if group == "Book":
		columns.append(col("title", "Title", "Data", 200))
	columns += [col("loans", "Loans", "Int", 80), col("borrowers", "Borrowers", "Int", 90), col("still_out", "Still Out", "Int", 85),
				col("returned_late", "Returned Late", "Int", 110), col("lost", "Lost", "Int", 70), col("fines", "Fines", "Currency", 100)]
	label_key = "title" if group == "Book" else "grp"
	labels, values = top(rows, label_key, "loans", n=12)
	chart = bar_chart(labels, values) if rows else None
	summary = [card("Loans", sum(r.loans for r in rows), indicator="Blue"), card("Still out", sum(r.still_out or 0 for r in rows)),
			   card("Lost", sum(r.lost or 0 for r in rows), indicator="Red" if any(r.lost for r in rows) else "Green"),
			   card("Fines charged", sum(r.fines or 0 for r in rows), "Currency")]
	return columns, rows, None, chart, summary
