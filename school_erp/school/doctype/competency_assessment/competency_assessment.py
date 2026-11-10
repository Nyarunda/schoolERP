# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.cbc import distribution_text, levels


class CompetencyAssessment(Document):
	def validate(self):
		from school_erp.api.cbc import cbc_rubric

		if not self.rubric:
			self.rubric = cbc_rubric()
		strand = frappe.get_cached_doc("CBC Strand", self.strand)
		if strand.subject != self.subject or strand.school_class != self.school_class:
			frappe.throw(_("Strand {0} is for {1} {2}, not {3} {4}").format(
				strand.strand_name, strand.school_class, strand.subject, self.school_class, self.subject))
		if self.sub_strand and self.sub_strand not in [r.sub_strand_name for r in strand.sub_strands]:
			frappe.throw(_("{0} is not a sub-strand of {1}").format(self.sub_strand, strand.strand_name))
		allowed = levels(self.rubric)
		in_stream = set(frappe.get_all("Student", filters={"stream": self.stream}, pluck="name"))
		seen = set()
		for r in self.results:
			if r.student in seen:
				frappe.throw(_("Row {0}: {1} is listed twice").format(r.idx, r.student_name or r.student))
			seen.add(r.student)
			if r.student not in in_stream:
				frappe.throw(_("Row {0}: {1} is not in {2}").format(r.idx, r.student_name or r.student, self.stream))
			if r.level and r.level not in allowed:
				frappe.throw(_("Row {0}: {1} is not a level on the {2} rubric ({3})").format(
					r.idx, r.level, self.rubric, ", ".join(allowed)))
		if not self.teacher:
			self.teacher = frappe.db.get_value("Teacher", {"user": frappe.session.user})
		self.assessed = sum(1 for r in self.results if r.level)
		self.distribution = distribution_text([r.level for r in self.results])
		self.title = f"{self.stream} · {frappe.db.get_value('Subject', self.subject, 'subject_name') or self.subject} · {strand.strand_name}"[:140]

	def before_submit(self):
		if not self.assessed:
			frappe.throw(_("Choose a level for at least one learner before submitting"))
