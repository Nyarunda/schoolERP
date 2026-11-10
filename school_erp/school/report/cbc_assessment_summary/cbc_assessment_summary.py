# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp import licensing
from school_erp.api.report_utils import bar_chart, card, col
from school_erp.logic.cbc import BANDS, band


@licensing.licensed("Competency Assessment")
def execute(filters=None):
	"""How learners are doing per learning area (or strand): counts at each CBC level, never a ranking."""
	f = frappe._dict(filters or {})
	group = f.group_by if f.group_by in ("Learning Area", "Strand", "Stream") else "Learning Area"
	cond, args = ["a.docstatus = 1"], {}
	for key, field in (("school_term", "a.school_term"), ("stream", "a.stream"), ("subject", "a.subject"),
					   ("school_class", "a.school_class")):
		if f.get(key):
			cond.append(f"{field} = %({key})s")
			args[key] = f.get(key)
	if f.from_date and not f.school_term:
		cond.append("a.assessment_date >= %(from_date)s")
		args["from_date"] = f.from_date
	if f.to_date and not f.school_term:
		cond.append("a.assessment_date <= %(to_date)s")
		args["to_date"] = f.to_date
	key = {"Learning Area": "a.subject", "Strand": "a.strand", "Stream": "a.stream"}[group]
	data = frappe.db.sql(f"""
		select {key} as grp, a.name as assessment, r.student, r.level
		from `tabCompetency Assessment` a join `tabCompetency Result` r on r.parent = a.name and r.parenttype = 'Competency Assessment'
		where {" and ".join(cond)}""", args, as_dict=True)
	groups = {}
	for d in data:
		g = groups.setdefault(d.grp, {"grp": d.grp, "assessments": set(), "learners": set(), **{b.lower(): 0 for b in BANDS},
									  "not_assessed": 0})
		g["assessments"].add(d.assessment)
		b = band(d.level)
		if b:
			g["learners"].add(d.student)
			g[b.lower()] += 1
		else:
			g["not_assessed"] += 1
	names = {}
	if group == "Strand":
		names = dict(frappe.get_all("CBC Strand", fields=["name", "strand_name"], as_list=True))
	elif group == "Learning Area":
		names = dict(frappe.get_all("Subject", fields=["name", "subject_name"], as_list=True))
	rows = []
	for g in groups.values():
		levelled = sum(g[b.lower()] for b in BANDS)
		rows.append({"grp": g["grp"], "label": names.get(g["grp"], g["grp"]), "assessments": len(g["assessments"]),
					 "learners": len(g["learners"]), "ee": g["ee"], "me": g["me"], "ae": g["ae"], "be": g["be"],
					 "not_assessed": g["not_assessed"],
					 "meeting_or_above": round((g["ee"] + g["me"]) / levelled * 100, 1) if levelled else 0.0})
	rows.sort(key=lambda r: str(r["label"]))
	link = {"Learning Area": "Subject", "Strand": "CBC Strand", "Stream": "Stream"}[group]
	columns = [col("grp", group, "Link", 140, link)]
	if group != "Stream":
		columns.append(col("label", "Name", "Data", 180))
	columns += [col("assessments", "Assessments", "Int", 105), col("learners", "Learners", "Int", 90),
				col("ee", "EE", "Int", 70), col("me", "ME", "Int", 70), col("ae", "AE", "Int", 70), col("be", "BE", "Int", 70),
				col("not_assessed", "Not Assessed", "Int", 105), col("meeting_or_above", "Meeting or Above %", "Percent", 150)]
	chart = bar_chart([str(r["label"]) for r in rows[:15]],
					  [(b, [r[b.lower()] for r in rows[:15]]) for b in BANDS], stacked=True) if rows else None
	total = {b: sum(r[b.lower()] for r in rows) for b in BANDS}
	levelled = sum(total.values())
	summary = [card("Assessments", len({d.assessment for d in data})),
			   card("Judgements recorded", levelled),
			   card("Meeting or above", round((total["EE"] + total["ME"]) / levelled * 100, 1) if levelled else 0, "Percent",
					indicator="Green"),
			   card("Below expectations", total["BE"], indicator="Red" if total["BE"] else "Green")]
	return columns, rows, None, chart, summary
