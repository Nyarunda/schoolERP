"""Exams: mark sheets, report card generation, publishing to parents."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, formatdate, get_url, now_datetime

from school_erp import licensing
from school_erp.logic.exams import (
	CBC_BANDS,
	KCSE_BANDS,
	auto_remark,
	bands_from_rows,
	build_results,
	competition_rank,
	subject_positions,
)


def install_default_scales():
	for name, system, bands in (("CBC", "CBC", CBC_BANDS), ("KCSE (8-4-4)", "8-4-4", KCSE_BANDS)):
		if frappe.db.exists("Grading Scale", name):
			continue
		frappe.get_doc({
			"doctype": "Grading Scale", "scale_name": name, "system": system,
			"bands": [{"min_score": lo, "max_score": hi, "grade": g, "points": p, "remark": r} for lo, hi, g, p, r in bands],
		}).insert(ignore_permissions=True)


def scale_bands(scale):
	return bands_from_rows([b.as_dict() for b in frappe.get_cached_doc("Grading Scale", scale).bands])


def exam_subjects(exam) -> list[str]:
	return [s.subject for s in exam.subjects] or frappe.get_all("Subject", pluck="name", order_by="subject_name")


def exam_streams(exam) -> list[str]:
	classes = [c.school_class for c in exam.classes]
	return frappe.get_all("Stream", filters={"school_class": ("in", classes or [""]), "is_active": 1}, pluck="name", order_by="name")


def subject_teacher(stream, subject, term):
	return frappe.db.sql(
		"""select ts.teacher from `tabTimetable Slot` ts join `tabTimetable` t on t.name = ts.parent
		where t.stream=%s and t.school_term=%s and ts.subject=%s and ifnull(ts.teacher,'')!='' limit 1""",
		(stream, term, subject))


# ----------------------------------------------------------------------------- progress
@frappe.whitelist()
def exam_progress(exam):
	"""Which stream x subject mark sheets are in."""
	doc = frappe.get_doc("Exam", exam)
	frappe.has_permission("Exam", "read", doc, throw=True)
	sheets = {(r.stream, r.subject): r for r in frappe.get_all(
		"Exam Mark Sheet", filters={"exam": exam, "docstatus": ("<", 2)},
		fields=["name", "stream", "subject", "docstatus", "entered", "approval_status"])}
	subjects = exam_subjects(doc)
	rows = []
	for st in exam_streams(doc):
		cells = []
		for sub in subjects:
			r = sheets.get((st, sub))
			state = "missing"
			if r:
				state = "done" if r.docstatus == 1 else {"Pending Approval": "pending", "Returned": "returned"}.get(r.approval_status, "draft")
			cells.append({"subject": sub, "sheet": r.name if r else None, "state": state})
		rows.append({"stream": st, "cells": cells})
	done = sum(1 for r in rows for c in r["cells"] if c["state"] == "done")
	total = sum(len(r["cells"]) for r in rows)
	pending = sum(1 for r in rows for c in r["cells"] if c["state"] == "pending")
	return {"subjects": subjects, "rows": rows, "done": done, "total": total, "pending": pending,
			"approval": _approval_on(), "to_approve": len(approval_queue_names(exam)) if pending else 0}


# ----------------------------------------------------------------------------- marks approval
def _approval_on():
	from school_erp.school.doctype.exam_mark_sheet.exam_mark_sheet import approval_required

	return approval_required()


def _decides_all(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & {"Head Teacher", "School Admin", "System Manager"})


def approval_queue_names(exam=None, user=None):
	"""Mark sheets waiting for this user's approval (everything pending for the Head Teacher)."""
	user = user or frappe.session.user
	filters = {"docstatus": 0, "approval_status": "Pending Approval"}
	if exam:
		filters["exam"] = exam
	if not _decides_all(user):
		if "Head of Department" not in frappe.get_roles(user):
			return []
		filters["reviewer"] = user
		filters["owner"] = ("!=", user)  # nobody approves the marks they entered themselves
	return frappe.get_all("Exam Mark Sheet", filters=filters, pluck="name")


@frappe.whitelist()
def approval_queue(exam):
	"""Pending sheets grouped by class, with the numbers an approver checks at a glance."""
	licensing.require("exams")
	names = approval_queue_names(exam)
	if not names:
		return []
	teacher_names = dict(frappe.get_all("Teacher", fields=["name", "teacher_name"], as_list=True))
	rows = frappe.get_all("Exam Mark Sheet", filters={"name": ("in", names)},
						  fields=["name", "school_class", "stream", "subject", "teacher", "entered", "average", "highest",
								  "lowest", "max_marks", "owner", "modified"], order_by="school_class, stream, subject")
	groups = {}
	for r in rows:
		r["teacher_name"] = teacher_names.get(r.teacher) or frappe.utils.get_fullname(r.owner)
		r["absent"] = frappe.db.count("Exam Mark", {"parent": r.name, "absent": 1})
		groups.setdefault(r.school_class, []).append(r)
	return [{"school_class": c, "sheets": s} for c, s in groups.items()]


@frappe.whitelist(methods=["POST"])
def approve_sheets(names):
	"""Approve several mark sheets at once (e.g. a whole class). Each goes through the Workflow's own checks."""
	from frappe.model.workflow import apply_workflow

	licensing.require("exams")
	names = frappe.parse_json(names) if isinstance(names, str) else names
	allowed = set(approval_queue_names())
	done, failed = [], []
	for name in names:
		if name not in allowed:
			failed.append({"name": name, "error": _("Not waiting for your approval")})
			continue
		frappe.db.savepoint("approve_sheet")
		try:
			apply_workflow(frappe.get_doc("Exam Mark Sheet", name), "Approve")
			done.append(name)
		except Exception as e:
			frappe.db.rollback(save_point="approve_sheet")
			frappe.clear_messages()
			failed.append({"name": name, "error": frappe.utils.strip_html(str(e))})
	return {"approved": len(done), "failed": failed}


# ----------------------------------------------------------------------------- report cards
@frappe.whitelist()
def generate_report_cards(exam):
	"""Build (or rebuild) a report card per student from the submitted mark sheets, with positions."""
	licensing.require("exams")
	doc = frappe.get_doc("Exam", exam)
	frappe.has_permission("Report Card", "create", throw=True)
	bands = scale_bands(doc.grading_scale)
	sheets = frappe.get_all("Exam Mark Sheet", filters={"exam": exam, "docstatus": 1},
							fields=["name", "stream", "school_class", "subject", "teacher", "max_marks"])
	if not sheets:
		frappe.throw(_("No submitted mark sheets yet for {0}").format(exam))

	marks = defaultdict(dict)  # student -> subject -> {marks, absent}
	out_of, teachers, student_stream = {}, {}, {}
	teacher_names = dict(frappe.get_all("Teacher", fields=["name", "teacher_name"], as_list=True))
	for sh in sheets:
		out_of[sh.subject] = flt(sh.max_marks) or flt(doc.max_marks) or 100
		teachers[(sh.stream, sh.subject)] = teacher_names.get(sh.teacher, "")
		for m in frappe.get_all("Exam Mark", filters={"parent": sh.name}, fields=["student", "marks", "absent"]):
			val = None if m.absent or not (m.marks or "").strip() else flt(m.marks)
			marks[m.student][sh.subject] = {"marks": val, "absent": bool(m.absent)}
			student_stream[m.student] = (sh.stream, sh.school_class)

	results = build_results(marks, out_of, bands)
	by_stream, by_class = defaultdict(dict), defaultdict(dict)
	for st, r in results.items():
		stream, cls = student_stream[st]
		by_stream[stream][st] = r["mean_percent"]
		by_class[cls][st] = r["mean_percent"]
	stream_rank = {s: competition_rank(v) for s, v in by_stream.items()}
	class_rank = {c: competition_rank(v) for c, v in by_class.items()}
	# subject positions within the stream
	sub_pos = {}
	for stream, members in by_stream.items():
		sub_pos[stream] = subject_positions({st: results[st] for st in members})

	previous = _previous_means(doc, list(results))
	created = 0
	for st, r in results.items():
		stream, cls = student_stream[st]
		name = frappe.db.get_value("Report Card", {"student": st, "exam": exam})
		rc = frappe.get_doc("Report Card", name) if name else frappe.new_doc("Report Card")
		keep_ct = rc.class_teacher_remark if name else None
		keep_ht = rc.head_teacher_remark if name else None
		rc.update({
			"student": st, "exam": exam, "school_term": doc.school_term, "stream": stream, "school_class": cls,
			"total_marks": r["total_marks"], "total_out_of": r["total_out_of"], "mean_percent": r["mean_percent"] or 0,
			"mean_grade": r["mean_grade"], "mean_points": r["mean_points"],
			"stream_position": stream_rank[stream].get(st) or 0, "stream_size": len(stream_rank[stream]),
			"class_position": class_rank[cls].get(st) or 0, "class_size": len(class_rank[cls]),
			"previous_mean": previous.get(st),
			"class_teacher_remark": keep_ct or auto_remark(r["mean_percent"], previous.get(st)),
			"head_teacher_remark": keep_ht,
		})
		rc.set("subjects", [])
		for sub in exam_subjects(doc):
			row = r["subjects"].get(sub)
			if not row:
				continue
			pos = sub_pos[stream].get(sub, {}).get(st)
			rc.append("subjects", {
				"subject": sub, "marks": row["marks"], "out_of": row["out_of"], "percent": row["percent"],
				"grade": row["grade"], "points": row["points"], "remark": row["remark"],
				"subject_position": f"{pos}/{len(sub_pos[stream].get(sub, {}))}" if pos else "",
				"teacher": teachers.get((stream, sub), ""),
			})
		rc.flags.ignore_permissions = True
		rc.save()
		created += 1
	doc.db_set("status", "Results Ready" if doc.status != "Published" else "Published")
	waiting = frappe.db.count("Exam Mark Sheet", {"exam": exam, "docstatus": 0})
	return {"report_cards": created, "not_included": waiting}


def _previous_means(exam, students):
	"""Mean % from the student's most recent earlier exam (for 'improved by' remarks)."""
	prev = frappe.db.sql(
		"""select rc.student, rc.mean_percent from `tabReport Card` rc join `tabExam` e on e.name = rc.exam
		where rc.student in %(s)s and rc.exam != %(exam)s and e.creation < %(created)s
		order by e.creation desc""",
		{"s": tuple(students) or ("",), "exam": exam.name, "created": exam.creation}, as_dict=True)
	out = {}
	for p in prev:
		out.setdefault(p.student, flt(p.mean_percent))
	return out


@frappe.whitelist()
def publish(exam, notify_parents=1):
	"""Make report cards visible on the parent portal and send them (email PDF + SMS summary)."""
	licensing.require("exams")
	frappe.has_permission("Exam", "write", throw=True)
	doc = frappe.get_doc("Exam", exam)
	cards = frappe.get_all("Report Card", filters={"exam": exam}, pluck="name")
	if not cards:
		frappe.throw(_("Generate the report cards first"))
	frappe.db.set_value("Report Card", {"exam": exam}, {"status": "Published", "published_on": now_datetime()})
	doc.db_set({"status": "Published", "published_on": now_datetime()})
	if int(notify_parents) and licensing.is_enabled("messaging"):
		frappe.enqueue("school_erp.api.exams.send_report_cards", queue="long", timeout=3600, exam=exam,
					   enqueue_after_commit=True, now=bool(frappe.flags.in_test))
	return {"published": len(cards)}


def send_report_cards(exam):
	from school_erp.api.messaging import email_student, sms_student

	s = frappe.get_cached_doc("School Settings")
	url = get_url("/parent")
	for name in frappe.get_all("Report Card", filters={"exam": exam, "sent_to_parents": 0}, pluck="name"):
		rc = frappe.get_doc("Report Card", name)
		student = frappe.get_doc("Student", rc.student)
		try:
			sms_student(student, s.report_card_sms, {
				"student_name": student.first_name, "exam": rc.exam, "mean_grade": rc.mean_grade,
				"mean_percent": f"{flt(rc.mean_percent):.1f}", "position": rc.stream_position, "size": rc.stream_size, "url": url,
			})
			_email_report_card(rc, student)
			rc.db_set("sent_to_parents", 1)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Report card send failed: {name}")


def _email_report_card(rc, student):
	from school_erp.school.doctype.student.student import get_guardian_contacts

	contacts = get_guardian_contacts(student, "email")
	if not contacts:
		return
	pdf = report_card_pdf(rc.name)
	frappe.sendmail(
		recipients=[c["email"] for c in contacts],
		subject=_("{0}: report card for {1}").format(rc.exam, student.student_name),
		message=_("Dear Parent,<br><br>Please find attached {0}'s report card for {1}. Mean grade: <b>{2}</b> ({3:.1f}%), position {4} of {5}.<br><br>{6}").format(
			student.first_name, rc.exam, rc.mean_grade, flt(rc.mean_percent), rc.stream_position, rc.stream_size,
			frappe.db.get_single_value("School Settings", "school_name") or ""),
		attachments=[{"fname": f"Report Card {student.name}.pdf", "fcontent": pdf}],
		reference_doctype="Report Card", reference_name=rc.name,
	)


def report_card_pdf(name):
	from frappe.utils.pdf import get_pdf

	html = frappe.render_template("school_erp/templates/report_card/body.html", report_card_context(name))
	page = frappe.render_template("school_erp/templates/fee_statement/page.html", {"body": html, "title": f"Report Card {name}"})
	return get_pdf(page, {"page-size": "A4", "margin-top": "10mm", "margin-bottom": "10mm", "margin-left": "10mm", "margin-right": "10mm"})


def report_card_context(name):
	"""Everything the report card template needs (also a Jinja helper for the print format)."""
	rc = frappe.get_doc("Report Card", name) if isinstance(name, str) else name
	s = frappe.get_cached_doc("School Settings")
	student = frappe.get_doc("Student", rc.student)
	exam = frappe.get_cached_doc("Exam", rc.exam)
	bands = scale_bands(exam.grading_scale)
	return {
		"rc": rc, "student": student, "exam": exam,
		"school": {"name": s.school_name, "motto": s.motto, "address": s.address, "phone": s.phone, "email": s.email,
				   "logo": get_url(s.school_logo) if s.school_logo else None, "accent": s.statement_accent_color or "#1f6f5c"},
		"bands": [{"range": f"{lo:g}-{hi:g}", "grade": g, "remark": r} for lo, hi, g, p, r in bands],
		"class_teacher": frappe.db.get_value("Teacher", frappe.db.get_value("Stream", rc.stream, "class_teacher"), "teacher_name") if rc.stream else "",
		"issued": formatdate(rc.published_on or now_datetime(), "d MMM yyyy"),
		"trend": (round(flt(rc.mean_percent) - flt(rc.previous_mean), 1) if rc.previous_mean else None),
	}


def render_report_card(name):
	"""Jinja helper used by the 'Report Card' print format."""
	return frappe.render_template("school_erp/templates/report_card/body.html", report_card_context(name))


@frappe.whitelist()
def download_report_card(name):
	rc = frappe.get_doc("Report Card", name)
	frappe.has_permission("Report Card", "read", rc, throw=True)
	frappe.local.response.filename = f"Report Card {rc.student} {rc.exam}.pdf"
	frappe.local.response.filecontent = report_card_pdf(name)
	frappe.local.response.type = "pdf"
