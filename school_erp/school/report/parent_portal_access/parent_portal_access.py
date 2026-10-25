# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from school_erp.api.report_utils import col

PARENT_ROLE = "Parent"


def execute(filters=None):
	f = frappe._dict(filters or {})
	cond, args = "", {}
	if f.school_class:
		cond += " and s.school_class = %(cls)s"; args["cls"] = f.school_class
	if f.stream:
		cond += " and s.stream = %(stream)s"; args["stream"] = f.stream
	rows = frappe.db.sql(f"""
		select g.guardian_name, g.relation, g.mobile_no, g.email, g.user,
			s.name student, s.student_name, coalesce(s.stream, s.school_class) stream,
			u.enabled, u.last_login, u.last_active,
			(select count(*) from `tabHas Role` r where r.parent = g.user and r.parenttype = 'User' and r.role = %(role)s) has_role
		from `tabStudent Guardian` g
		join `tabStudent` s on s.name = g.parent
		left join `tabUser` u on u.name = g.user
		where g.parenttype = 'Student' and s.status in ('Active', 'Suspended') {cond}
		order by g.guardian_name, s.student_name""", {"role": PARENT_ROLE, **args}, as_dict=True)

	# One row per parent: a guardian listed on several siblings shares one login
	parents = {}
	for r in rows:
		key = r.user or (r.mobile_no or "").strip() or (r.email or "").strip().lower() or f"{r.guardian_name}|{r.student}"
		p = parents.get(key)
		if not p:
			p = parents[key] = frappe._dict(r, students=[], streams=[])
		p.students.append(r.student_name)
		if r.stream and r.stream not in p.streams:
			p.streams.append(r.stream)
		p.first_student = p.get("first_student") or r.student

	out = []
	for p in parents.values():
		p.status = _status(p)
		if f.status and p.status != f.status:
			continue
		p.children = ", ".join(p.students)
		p.child_count = len(p.students)
		p.classes = ", ".join(p.streams)
		p.student = p.first_student
		out.append(p)

	columns = [
		col("status", "Portal Access", "Data", 130),
		col("guardian_name", "Parent / Guardian", "Data", 170), col("relation", "Relation", "Data", 85),
		col("mobile_no", "Mobile", "Data", 120), col("email", "Email", "Data", 170),
		col("children", "Children", "Data", 200), col("child_count", "No.", "Int", 50), col("classes", "Class", "Data", 120),
		col("user", "Login", "Link", 190, "User"), col("last_login", "Last Login", "Datetime", 150),
		col("student", "Student", "Link", 130, "Student"),
	]
	return columns, out, None, None, _summary(out)


def _status(p):
	if p.user:
		if not p.enabled:
			return "Login Disabled"
		if not p.has_role:
			return "Missing Parent Role"
		return "Active" if p.last_login else "Never Logged In"
	return "No Login" if (p.mobile_no or p.email) else "No Contact"


def _summary(rows):
	count = lambda *states: sum(1 for r in rows if r.status in states)  # noqa: E731
	return [
		{"value": len(rows), "label": _("Parents"), "datatype": "Int"},
		{"value": count("Active"), "label": _("Using the portal"), "datatype": "Int", "indicator": "Green"},
		{"value": count("Never Logged In"), "label": _("Never logged in"), "datatype": "Int", "indicator": "Blue"},
		{"value": count("No Login", "Login Disabled", "Missing Parent Role"), "label": _("No access"), "datatype": "Int", "indicator": "Orange"},
		{"value": count("No Contact"), "label": _("No phone or email"), "datatype": "Int", "indicator": "Red"},
	]
