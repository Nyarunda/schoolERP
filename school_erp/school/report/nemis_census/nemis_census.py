# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from school_erp.api.report_utils import bar_chart, card, col
from school_erp.logic.nemis import age_gender_matrix, age_on, class_summary, missing_items

VIEWS = ("Learner List", "Class Summary", "Age & Gender")


def execute(filters=None):
	"""Everything the Ministry's NEMIS/KEMIS census and KNEC registration ask for, ready to export (Menu > Export)."""
	f = frappe._dict(filters or {})
	view = f.view if f.view in VIEWS else "Learner List"
	cond, args = ["s.status = %(status)s"], {"status": f.status or "Active"}
	if f.school_class:
		cond.append("s.school_class = %(cls)s")
		args["cls"] = f.school_class
	if f.stream:
		cond.append("s.stream = %(stream)s")
		args["stream"] = f.stream
	learners = frappe.db.sql(f"""
		select s.name as student, s.student_name, s.admission_number, s.upi_number, s.birth_certificate_no,
			s.assessment_number, s.gender, s.date_of_birth, s.school_class, s.stream, s.boarding_type, s.nationality,
			s.county, s.sub_county, s.special_needs, s.special_needs_details, s.previous_school, s.primary_guardian,
			s.primary_phone
		from `tabStudent` s left join `tabSchool Class` c on c.name = s.school_class
		where {" and ".join(cond)}
		order by c.level, s.stream, s.student_name""", args, as_dict=True)
	today = getdate(f.census_date or nowdate())
	for r in learners:
		r["age"] = age_on(r.date_of_birth, today)
		r["missing"] = ", ".join(missing_items(r))
	if f.missing_only:
		learners = [r for r in learners if r.missing]

	missing_upi = sum(1 for r in learners if not r.upi_number)
	missing_cert = sum(1 for r in learners if not r.birth_certificate_no)
	summary = [card("Learners", len(learners), indicator="Blue"),
			   card("Missing UPI", missing_upi, indicator="Red" if missing_upi else "Green"),
			   card("Missing birth certificate", missing_cert, indicator="Orange" if missing_cert else "Green"),
			   card("Special needs", sum(1 for r in learners if r.special_needs))]

	if view == "Class Summary":
		rows = class_summary(learners)
		columns = [col("school_class", "Class", "Link", 120, "School Class"), col("boys", "Boys", "Int", 80),
				   col("girls", "Girls", "Int", 80), col("total", "Total", "Int", 80),
				   col("special_needs", "Special Needs", "Int", 110), col("missing_upi", "Missing UPI", "Int", 110),
				   col("missing_birth_cert", "Missing Birth Cert", "Int", 140),
				   col("percent_complete", "Records Complete %", "Percent", 150)]
		chart = bar_chart([r["school_class"] for r in rows], [(_("Boys"), [r["boys"] for r in rows]),
															  (_("Girls"), [r["girls"] for r in rows])], stacked=True) if rows else None
		return columns, rows, None, chart, summary

	if view == "Age & Gender":
		matrix = age_gender_matrix(learners, today)
		rows = [{"age": _("Not recorded") if age is None else age, "boys": c["Male"], "girls": c["Female"],
				 "total": c["Male"] + c["Female"]} for age, c in matrix.items()]
		columns = [col("age", "Age (years)", "Data", 120), col("boys", "Boys", "Int", 90), col("girls", "Girls", "Int", 90),
				   col("total", "Total", "Int", 90)]
		chart = bar_chart([str(r["age"]) for r in rows], [(_("Boys"), [r["boys"] for r in rows]),
														  (_("Girls"), [r["girls"] for r in rows])], stacked=True) if rows else None
		return columns, rows, None, chart, summary

	columns = [
		col("student", "Student ID", "Link", 120, "Student"), col("student_name", "Name", "Data", 180),
		col("upi_number", "UPI", "Data", 110), col("birth_certificate_no", "Birth Cert No.", "Data", 120),
		col("assessment_number", "KNEC Assessment No.", "Data", 150), col("gender", "Gender", "Data", 80),
		col("date_of_birth", "Date of Birth", "Date", 105), col("age", "Age", "Int", 60),
		col("school_class", "Class", "Link", 100, "School Class"), col("stream", "Stream", "Link", 120, "Stream"),
		col("admission_number", "Adm. No.", "Data", 100), col("boarding_type", "Day/Boarder", "Data", 95),
		col("nationality", "Nationality", "Data", 100), col("county", "County", "Data", 110),
		col("sub_county", "Sub-County", "Data", 110), col("special_needs", "Special Needs", "Check", 100),
		col("special_needs_details", "Special Needs Details", "Data", 160), col("previous_school", "Previous School", "Data", 150),
		col("primary_guardian", "Guardian", "Data", 150), col("primary_phone", "Guardian Phone", "Data", 120),
		col("missing", "Missing for Census", "Data", 170),
	]
	return columns, learners, None, None, summary
