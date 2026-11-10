# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col, date_range
from school_erp.logic.health import OUTCOMES, frequent_visitors, has_fever


@licensing.licensed("Sick Bay Visit")
def execute(filters=None):
	"""Every sick bay visit in a period, or (Frequent Visitors) the learners seen most often."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = ["date(visit_datetime) between %(fd)s and %(td)s"], {"fd": fd, "td": td}
	if f.school_class:
		cond.append("school_class = %(cls)s")
		args["cls"] = f.school_class
	if f.outcome in OUTCOMES:
		cond.append("outcome = %(outcome)s")
		args["outcome"] = f.outcome
	rows = frappe.db.sql(f"""select name, visit_datetime, student, student_name, school_class, symptoms, temperature, assessment,
			treatment, medication_given, outcome, referred_to, parent_notified, attended_by
		from `tabSick Bay Visit` where {" and ".join(cond)} order by visit_datetime desc""", args, as_dict=True)
	by_outcome = {o: sum(1 for r in rows if r.outcome == o) for o in OUTCOMES}
	summary = [card("Visits", len(rows), indicator="Blue"), card("Sent home", by_outcome["Sent home"], indicator="Orange"),
			   card("Referred", by_outcome["Referred to hospital"], indicator="Red" if by_outcome["Referred to hospital"] else "Green"),
			   card("With fever", sum(1 for r in rows if has_fever(r.temperature)))]
	chart = bar_chart([_(o) for o in OUTCOMES], list(by_outcome.values())) if rows else None
	if f.view == "Frequent Visitors":
		freq = frequent_visitors(rows, int(f.min_visits or 3))
		columns = [col("student", "Learner", "Link", 130, "Student"), col("student_name", "Name", "Data", 200),
				   col("visits", "Visits", "Int", 80)]
		return columns, freq, None, None, summary
	for r in rows:
		r["fever"] = 1 if has_fever(r.temperature) else 0
	columns = [col("name", "Visit", "Link", 120, "Sick Bay Visit"), col("visit_datetime", "Seen At", "Datetime", 145),
			   col("student_name", "Learner", "Data", 170), col("school_class", "Class", "Link", 90, "School Class"),
			   col("symptoms", "Symptoms", "Data", 200), col("temperature", "Temp °C", "Float", 80), col("fever", "Fever", "Check", 65),
			   col("treatment", "Treatment", "Data", 170), col("outcome", "Outcome", "Data", 150), col("referred_to", "Referred To", "Data", 140),
			   col("parent_notified", "Parent Told", "Check", 90), col("attended_by", "Attended By", "Link", 140, "User")]
	return columns, rows, None, chart, summary
