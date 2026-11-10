"""Bench tests: CBC strands, competency assessments, progress reports and the summary report."""

import frappe

from school_erp.tests.test_integration import TestCase, setup_school


class TestCbcAssessment(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		cls.subject = frappe.get_all("Subject", pluck="name", limit=1)[0]
		cls.strand = frappe.get_doc({"doctype": "CBC Strand", "strand_name": "Numbers " + frappe.generate_hash(length=5),
									 "subject": cls.subject, "school_class": "Grade 4",
									 "sub_strands": [{"sub_strand_name": "Whole numbers"}, {"sub_strand_name": "Fractions"}]}).insert().name
		cls.kids = [cls.make_student(n).name for n in ("Achieng", "Baraka")]
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	@staticmethod
	def make_student(first):
		return frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": "Cbc", "stream": "Grade 4 Test", "gender": "Female",
			"guardians": [{"guardian_name": "Mama " + first, "relation": "Mother", "mobile_no": "0712345678"}],
		}).insert()

	def assessment(self, levels, **kw):
		return frappe.get_doc({
			"doctype": "Competency Assessment", "school_term": self.term, "stream": "Grade 4 Test", "subject": self.subject,
			"strand": self.strand, "sub_strand": "Fractions",
			"results": [{"student": s, "level": lvl} for s, lvl in zip(self.kids, levels)], **kw,
		})

	def test_strand_rejects_duplicate_sub_strands(self):
		doc = frappe.get_doc({"doctype": "CBC Strand", "strand_name": "Dup", "subject": self.subject, "school_class": "Grade 4",
							  "sub_strands": [{"sub_strand_name": "A"}, {"sub_strand_name": "a"}]})
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_assessment_validates_levels_and_stream(self):
		with self.assertRaises(frappe.ValidationError):
			self.assessment(["EE1", "ME"]).insert()  # 8-level code on the default 4-level rubric
		with self.assertRaises(frappe.ValidationError):
			self.assessment(["EE", "ME"], sub_strand="Not a sub-strand").insert()
		doc = self.assessment(["EE", ""]).insert()
		self.assertEqual(doc.rubric, "4-level (EE / ME / AE / BE)")
		self.assertEqual((doc.assessed, doc.distribution), (1, "EE 1"))

	def test_progress_reports_from_assessments(self):
		from school_erp.api.cbc import generate_progress_reports, portal_reports, publish_progress_reports, render_cbc_progress_report

		self.assessment(["EE", "AE"]).insert().submit()
		self.assessment(["ME", "AE"], assessment_type="Project").insert().submit()
		out = generate_progress_reports(self.term, "Grade 4 Test")
		self.assertGreaterEqual(out["progress_reports"], 2)
		name = frappe.db.get_value("CBC Progress Report", {"student": self.kids[0], "school_term": self.term})
		rep = frappe.get_doc("CBC Progress Report", name)
		area = next(a for a in rep.areas if a.subject == self.subject)
		self.assertEqual(area.level, "EE")  # EE + ME on one strand = 3.5 -> EE
		area.teacher_comment = "Keeps trying"
		rep.save()
		generate_progress_reports(self.term, "Grade 4 Test")  # a rebuild keeps what the teacher typed
		rebuilt = frappe.get_doc("CBC Progress Report", name)
		self.assertEqual(next(a for a in rebuilt.areas if a.subject == self.subject).teacher_comment, "Keeps trying")

		self.assertEqual(portal_reports(self.kids[0]), [])  # drafts stay off the portal
		publish_progress_reports(self.term, "Grade 4 Test", notify_parents=0)
		self.assertEqual(len(portal_reports(self.kids[0])), 1)
		self.assertIn("LEARNER PROGRESS REPORT", render_cbc_progress_report(name))

	def test_summary_report(self):
		from school_erp.school.report.cbc_assessment_summary.cbc_assessment_summary import execute

		self.assessment(["BE", "ME"]).insert().submit()
		_c, rows, _m, _chart, summary = execute({"school_term": self.term, "group_by": "Strand"})
		row = next(r for r in rows if r["grp"] == self.strand)
		self.assertGreaterEqual(row["be"], 1)
		self.assertTrue(summary)
