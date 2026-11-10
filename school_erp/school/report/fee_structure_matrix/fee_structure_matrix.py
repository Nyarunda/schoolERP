# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range, bar_chart, card


def execute(filters=None):
	"""Fees differ per class and per term: one row per class, one column per term (and boarding type)."""
	f = frappe._dict(filters or {})
	year = f.school_year or frappe.db.get_value("School Year", {"is_current": 1})
	from school_erp.api.billing import fee_matrix

	if not year:
		return [], []
	m = fee_matrix(year)
	bts = sorted({bt for r in m["rows"] for t in m["terms"] for bt in r[t]}) or ["All"]
	columns = [col("school_class", "Class", "Link", 120, "School Class")]
	for t in m["terms"]:
		for bt in bts:
			label = t if bts == ["All"] else f"{t} ({bt})"
			columns.append(col(f"{t}|{bt}", label, "Currency", 150))
	data = []
	for r in m["rows"]:
		row = {"school_class": r["school_class"]}
		for t in m["terms"]:
			general = r[t].get("All", 0)
			for bt in bts:
				row[f"{t}|{bt}"] = r[t].get(bt, 0) + (general if bt != "All" else 0) if r[t] else None
		data.append(row)
	# each class's fee per term (the general / day rate), terms side by side; capped at 4 series
	keys = [f"{t}|{bts[0]}" for t in m["terms"]][:4]
	chart = bar_chart([r["school_class"] for r in data], [(k.split("|")[0], [flt(r.get(k)) for r in data]) for k in keys], money=True) if data else None
	totals = [sum(flt(r.get(k)) for k in keys) for r in data]
	summary = [card("Classes", len(data)), card("Terms", len(m["terms"])),
			   card("Highest year total", max(totals) if totals else 0, "Currency", indicator="Blue"),
			   card("Lowest year total", min(totals) if totals else 0, "Currency")]
	return columns, data, None, chart, summary
