# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col
from school_erp.logic.boarding import occupancy


@licensing.licensed("Dormitory")
def execute(filters=None):
	f = frappe._dict(filters or {})
	dorm_filters = {"is_active": 1}
	if f.gender:
		dorm_filters["gender"] = f.gender
	dorms = frappe.get_all("Dormitory", filters=dorm_filters, fields=["name", "gender", "capacity", "house_parent"], order_by="name")
	counts = dict(frappe.db.sql("""select dormitory, count(*) from `tabBoarding Allocation` where status = 'Active'
		group by dormitory"""))
	rows = []
	for d in dorms:
		o = occupancy(d.capacity, counts.get(d.name, 0))
		rows.append({"dormitory": d.name, "gender": d.gender, "house_parent": d.house_parent, **o})
	unplaced = frappe.db.sql("""select count(*) from `tabStudent` s where s.status = 'Active' and s.boarding_type = 'Boarder'
		and not exists (select 1 from `tabBoarding Allocation` a where a.student = s.name and a.status = 'Active')""")[0][0]
	columns = [col("dormitory", "Dormitory", "Link", 160, "Dormitory"), col("gender", "For", "Data", 80),
			   col("capacity", "Beds", "Int", 80), col("occupied", "Occupied", "Int", 90), col("free", "Free", "Int", 80),
			   col("percent", "Full %", "Percent", 90), col("house_parent", "House Parent", "Link", 160, "User")]
	chart = bar_chart([r["dormitory"] for r in rows], [(_("Occupied"), [r["occupied"] for r in rows]),
													   (_("Free"), [r["free"] for r in rows])], stacked=True) if rows else None
	summary = [card("Beds", sum(r["capacity"] for r in rows), indicator="Blue"), card("Occupied", sum(r["occupied"] for r in rows)),
			   card("Free", sum(r["free"] for r in rows), indicator="Green"),
			   card("Boarders without a bed", unplaced, indicator="Red" if unplaced else "Green")]
	return columns, rows, None, chart, summary
