# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CBCStrand(Document):
	def validate(self):
		self.strand_name = " ".join((self.strand_name or "").split())
		dup = frappe.db.get_value("CBC Strand", {"subject": self.subject, "school_class": self.school_class,
												 "strand_name": self.strand_name, "name": ("!=", self.name)})
		if dup:
			frappe.throw(_("{0} already has the strand {1} for {2} ({3})").format(self.subject, self.strand_name, self.school_class, dup))
		seen = set()
		for row in self.sub_strands:
			row.sub_strand_name = " ".join((row.sub_strand_name or "").split())
			key = row.sub_strand_name.lower()
			if key in seen:
				frappe.throw(_("Row {0}: sub-strand {1} is listed twice").format(row.idx, row.sub_strand_name))
			seen.add(key)
