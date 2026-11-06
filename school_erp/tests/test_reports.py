"""Every School report runs with typical filters and returns well-formed charts and summary cards."""

import frappe
import frappe.desk.query_report
from frappe.utils import add_days, nowdate

from school_erp.tests.test_integration import TestCase, setup_school


class TestReports(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)

	@classmethod
	def tearDownClass(cls):
		cls._pub.stop()
		super().tearDownClass()

	def test_every_report_runs(self):
		frappe.set_user("Administrator")
		filters = {"from_date": add_days(nowdate(), -90), "to_date": nowdate(), "school_term": self.term, "term": self.term,
				   "date": nowdate(), "as_on": nowdate(), "company": self.company}
		names = frappe.get_all("Report", filters={"module": "School", "is_standard": "Yes"}, pluck="name")
		self.assertGreaterEqual(len(names), 20)
		for name in names:
			with self.subTest(report=name):
				res = frappe.desk.query_report.run(name, filters=filters)
				chart = res.get("chart")
				if chart:
					data = chart["data"]
					self.assertTrue(all(len(d["values"]) == len(data["labels"]) for d in data["datasets"]), name)
					self.assertLessEqual(len(data["datasets"]), 4, f"{name}: more series than the palette has slots")
				for c in res.get("report_summary") or []:
					self.assertIn("label", c)
					self.assertIn("value", c)
