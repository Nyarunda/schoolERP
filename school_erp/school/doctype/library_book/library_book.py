# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.library import copy_counts


class LibraryBook(Document):
	def validate(self):
		self.title = " ".join((self.title or "").split())
		self.isbn = (self.isbn or "").replace("-", "").replace(" ", "") or None
		seen = set()
		for c in self.copies:
			c.accession_no = (c.accession_no or "").strip().upper()
			if c.accession_no in seen:
				frappe.throw(_("Row {0}: accession number {1} is listed twice").format(c.idx, c.accession_no))
			seen.add(c.accession_no)
			other = frappe.db.get_value("Library Book Copy", {"accession_no": c.accession_no, "parent": ("!=", self.name),
															   "parenttype": "Library Book"}, "parent")
			if other:
				frappe.throw(_("Accession number {0} already belongs to {1}").format(c.accession_no, other))
		if not self.is_new():
			on_loan = set(frappe.get_all("Library Loan", filters={"book": self.name, "status": "On Loan"}, pluck="accession_no"))
			for c in self.copies:  # a copy that is out stays On Loan until it is returned through its loan
				if c.accession_no in on_loan:
					c.status = "On Loan"
				elif c.status == "On Loan":
					c.status = "Available"
			missing = on_loan - seen
			if missing:
				frappe.throw(_("Copies {0} are out on loan and can't be removed").format(", ".join(sorted(missing))))
		counts = copy_counts([c.status for c in self.copies])
		self.total_copies, self.available_copies = counts["total"], counts["available"]
