# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col, date_range


@licensing.licensed("Visitor Log")
def execute(filters=None):
	"""Everyone who came through the gate, and who is still on the premises."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = ["date(time_in) between %(fd)s and %(td)s"], {"fd": fd, "td": td}
	if f.on_premises:
		cond = ["status = 'On premises'"]
	if f.purpose:
		cond.append("purpose = %(purpose)s")
		args["purpose"] = f.purpose
	rows = frappe.db.sql(f"""select name, time_in, time_out, visitor_name, phone, id_number, organisation, purpose, person_to_see,
			student, vehicle_registration, badge_number, status, minutes_on_premises
		from `tabVisitor Log` where {" and ".join(cond)} order by time_in desc""", args, as_dict=True)
	columns = [col("name", "Entry", "Link", 120, "Visitor Log"), col("time_in", "In", "Datetime", 145), col("time_out", "Out", "Datetime", 145),
			   col("visitor_name", "Visitor", "Data", 170), col("phone", "Phone", "Data", 115), col("id_number", "ID No.", "Data", 105),
			   col("organisation", "Organisation", "Data", 140), col("purpose", "Purpose", "Data", 130),
			   col("person_to_see", "To See", "Data", 130), col("student", "Learner", "Link", 110, "Student"),
			   col("vehicle_registration", "Vehicle", "Data", 95), col("badge_number", "Badge", "Data", 75),
			   col("minutes_on_premises", "Minutes", "Int", 80), col("status", "Status", "Data", 105)]
	by_purpose = {}
	for r in rows:
		by_purpose[r.purpose] = by_purpose.get(r.purpose, 0) + 1
	still_in = sum(1 for r in rows if r.status == "On premises")
	summary = [card("Visitors", len(rows), indicator="Blue"), card("Still on premises", still_in, indicator="Orange" if still_in else "Green")]
	chart = bar_chart(list(by_purpose), list(by_purpose.values())) if rows else None
	return columns, rows, None, chart, summary
