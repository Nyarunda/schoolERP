# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col, date_range
from school_erp.logic.admissions import STATUSES, funnel


@licensing.licensed("Admission Application")
def execute(filters=None):
	"""Applications by class and status for a period, with how many became students."""
	f = frappe._dict(filters or {})
	fd, td = date_range(f)
	cond, args = ["date(a.creation) between %(fd)s and %(td)s"], {"fd": fd, "td": td}
	if f.applying_for_class:
		cond.append("a.applying_for_class = %(cls)s")
		args["cls"] = f.applying_for_class
	if f.intake_term:
		cond.append("a.intake_term = %(term)s")
		args["term"] = f.intake_term
	if f.source:
		cond.append("a.source = %(source)s")
		args["source"] = f.source
	data = frappe.db.sql(f"""select a.applying_for_class, a.status from `tabAdmission Application` a
		left join `tabSchool Class` c on c.name = a.applying_for_class
		where {" and ".join(cond)} order by c.level""", args, as_dict=True)
	by_class = {}
	for d in data:
		by_class.setdefault(d.applying_for_class, []).append(d)
	rows = []
	for cls, items in by_class.items():
		fn = funnel(items)
		rows.append({"applying_for_class": cls, "total": fn["total"], "open": fn["open"],
					 **{s.lower().replace(" ", "_"): fn["counts"][s] for s in STATUSES}, "conversion": fn["conversion"]})
	columns = [col("applying_for_class", "Class", "Link", 120, "School Class"), col("total", "Applications", "Int", 105),
			   col("open", "Still Open", "Int", 90)]
	columns += [col(s.lower().replace(" ", "_"), s, "Int", 95) for s in STATUSES]
	columns.append(col("conversion", "Admitted of Decided %", "Percent", 160))
	everything = funnel(data)
	chart = bar_chart([_(s) for s in STATUSES], [everything["counts"][s] for s in STATUSES]) if data else None
	summary = [card("Applications", everything["total"], indicator="Blue"), card("Still open", everything["open"], indicator="Orange"),
			   card("Admitted", everything["counts"]["Admitted"], indicator="Green"),
			   card("Admitted of decided", everything["conversion"], "Percent")]
	return columns, rows, None, chart, summary
