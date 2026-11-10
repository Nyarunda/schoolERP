"""CBC competency assessment: learners for a stream, termly progress reports, publishing to parents."""

import frappe
from frappe import _
from frappe.utils import formatdate, get_url, now_datetime

from school_erp import licensing
from school_erp.logic.cbc import FOUR_LEVEL, roll_up, strengths_and_gaps
from school_erp.logic.cbc import rubric as rubric_rows


def cbc_rubric() -> str:
	return frappe.db.get_single_value("CBC Settings", "rubric") or FOUR_LEVEL


@frappe.whitelist()
def rubric_levels(rubric=None):
	"""Levels of an assessment's own rubric (or the school's current one for a new assessment)."""
	name = rubric or cbc_rubric()
	return {"rubric": name, "levels": [{"level": lvl, "points": pts, "descriptor": desc} for lvl, pts, desc in rubric_rows(name)]}


@frappe.whitelist()
def stream_students(stream):
	licensing.require("exams")
	frappe.has_permission("Competency Assessment", "create", throw=True)
	return frappe.get_all("Student", filters={"stream": stream, "status": "Active"},
						  fields=["name as student", "student_name"], order_by="student_name")


@frappe.whitelist()
def sub_strands(strand):
	doc = frappe.get_doc("CBC Strand", strand)
	frappe.has_permission("CBC Strand", "read", doc, throw=True)
	return [r.sub_strand_name for r in doc.sub_strands]


# ----------------------------------------------------------------------------- progress reports
@frappe.whitelist()
def generate_progress_reports(school_term, stream=None):
	"""Build (or rebuild) one progress report per learner for the term from the submitted assessments.
	Comments a teacher has already typed on a report are kept."""
	licensing.require("exams")
	frappe.has_permission("CBC Progress Report", "create", throw=True)
	rub = cbc_rubric()
	filters = {"school_term": school_term, "docstatus": 1}
	if stream:
		filters["stream"] = stream
	assessments = frappe.get_all("Competency Assessment", filters=filters,
								 fields=["name", "stream", "school_class", "subject", "strand", "assessment_date"],
								 order_by="assessment_date, creation")
	if not assessments:
		frappe.throw(_("No submitted competency assessments for {0} yet").format(school_term))
	meta = {a.name: a for a in assessments}
	order = {a.name: i for i, a in enumerate(assessments)}
	rows = frappe.get_all("Competency Result", filters={"parenttype": "Competency Assessment", "parent": ("in", list(meta))},
						  fields=["parent", "student", "level", "comment"])
	rows.sort(key=lambda r: order[r.parent])  # oldest first, so the newest comment wins below
	results, comments, placement = [], {}, {}
	for r in rows:
		a = meta[r.parent]
		results.append({"student": r.student, "subject": a.subject, "strand": a.strand, "level": r.level})
		if (r.comment or "").strip():
			comments[(r.student, a.subject)] = r.comment.strip()
		placement[r.student] = (a.stream, a.school_class)
	areas = roll_up(results, rub)
	names = dict(frappe.get_all("Subject", fields=["name", "subject_name"], as_list=True))
	built = 0
	for student, subjects in areas.items():
		stream_name, cls = placement[student]
		existing = frappe.db.get_value("CBC Progress Report", {"student": student, "school_term": school_term})
		doc = frappe.get_doc("CBC Progress Report", existing) if existing else frappe.new_doc("CBC Progress Report")
		typed = {a.subject: a.teacher_comment for a in doc.get("areas", []) if (a.teacher_comment or "").strip()}
		strong, weak = strengths_and_gaps(subjects, names)
		doc.update({"student": student, "school_term": school_term, "stream": stream_name, "school_class": cls, "rubric": rub,
					"strengths": strong, "areas_to_improve": weak})
		doc.set("areas", [])
		for subject in sorted(subjects, key=lambda s: names.get(s, s)):
			a = subjects[subject]
			doc.append("areas", {"subject": subject, "level": a["level"], "descriptor": a["descriptor"],
								 "strands_assessed": a["strands"], "assessments": a["assessments"],
								 "average_points": a["points"],
								 "teacher_comment": typed.get(subject) or comments.get((student, subject)) or ""})
		doc.flags.ignore_permissions = True
		doc.save()
		built += 1
	return {"progress_reports": built, "assessments": len(assessments)}


@frappe.whitelist()
def publish_progress_reports(school_term, stream=None, notify_parents=1):
	licensing.require("exams")
	frappe.has_permission("CBC Progress Report", "write", throw=True)
	filters = {"school_term": school_term}
	if stream:
		filters["stream"] = stream
	names = frappe.get_all("CBC Progress Report", filters=filters, pluck="name")
	if not names:
		frappe.throw(_("Generate the progress reports for {0} first").format(school_term))
	frappe.db.set_value("CBC Progress Report", {"name": ("in", names), "status": "Draft"},
						{"status": "Published", "published_on": now_datetime()})
	if int(notify_parents) and licensing.is_enabled("messaging"):
		frappe.enqueue("school_erp.api.cbc.send_progress_reports", queue="long", timeout=3600, names=names,
					   enqueue_after_commit=True, now=bool(frappe.flags.in_test))
	return {"published": len(names)}


def send_progress_reports(names):
	from school_erp.api.messaging import sms_student

	s = frappe.get_cached_doc("School Settings")
	template = frappe.db.get_single_value("CBC Settings", "progress_sms") or ""
	url = get_url("/parent")
	for name in names:
		rc = frappe.db.get_value("CBC Progress Report", name, ["student", "school_term", "sent_to_parents", "status"], as_dict=True)
		if not rc or rc.sent_to_parents or rc.status != "Published":
			continue
		try:
			student = frappe.get_doc("Student", rc.student)
			term = frappe.db.get_value("School Term", rc.school_term, "term_name") or rc.school_term
			sms_student(student, template, {"student_name": student.first_name, "term": term, "url": url,
											"school_name": s.school_name or ""})
			frappe.db.set_value("CBC Progress Report", name, "sent_to_parents", 1)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"CBC progress report SMS failed: {name}")


# ----------------------------------------------------------------------------- printing
def progress_report_context(name):
	doc = frappe.get_doc("CBC Progress Report", name) if isinstance(name, str) else name
	s = frappe.get_cached_doc("School Settings")
	settings = frappe.get_cached_doc("CBC Settings")
	names = dict(frappe.get_all("Subject", fields=["name", "subject_name"], as_list=True))
	return {
		"rc": doc, "student": frappe.get_doc("Student", doc.student),
		"term": frappe.db.get_value("School Term", doc.school_term, "term_name") or doc.school_term,
		"areas": [{**a.as_dict(), "subject_name": names.get(a.subject, a.subject)} for a in doc.areas],
		"key": [{"level": lvl, "descriptor": desc} for lvl, _p, desc in rubric_rows(doc.rubric)],
		"footer": settings.report_footer,
		"school": {"name": s.school_name, "motto": s.motto, "address": s.address, "phone": s.phone,
				   "logo": get_url(s.school_logo) if s.school_logo else None, "accent": s.statement_accent_color or "#1f6f5c"},
		"class_teacher": frappe.db.get_value("Teacher", frappe.db.get_value("Stream", doc.stream, "class_teacher"), "teacher_name") if doc.stream else "",
		"issued": formatdate(doc.published_on or now_datetime(), "d MMM yyyy"),
	}


def render_cbc_progress_report(name):
	"""Jinja helper used by the 'CBC Progress Report' print format."""
	return frappe.render_template("school_erp/templates/cbc_report/body.html", progress_report_context(name))


def progress_report_pdf(name):
	from frappe.utils.pdf import get_pdf

	html = render_cbc_progress_report(name)
	page = frappe.render_template("school_erp/templates/fee_statement/page.html", {"body": html, "title": f"CBC Progress Report {name}"})
	return get_pdf(page, {"page-size": "A4", "margin-top": "10mm", "margin-bottom": "10mm", "margin-left": "10mm", "margin-right": "10mm"})


@frappe.whitelist()
@licensing.licensed("CBC Progress Report")
def download_progress_report(name):
	"""Staff with read access, or a parent of the learner once the report is published."""
	from school_erp.api.portal import _as_admin, _require_portal, assert_parent_of

	doc = frappe.get_doc("CBC Progress Report", name)
	if frappe.has_permission("CBC Progress Report", "read", doc):
		pdf = progress_report_pdf(name)
	else:
		_require_portal()
		assert_parent_of(doc.student)
		if doc.status != "Published":
			raise frappe.PermissionError
		pdf = _as_admin(progress_report_pdf, name)
	frappe.local.response.filename = f"CBC Progress Report {doc.student} {doc.school_term}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def portal_reports(student):
	"""Published progress reports for the parent portal, newest first (template-ready)."""
	if not licensing.is_enabled("exams"):
		return []
	out = []
	names = dict(frappe.get_all("Subject", fields=["name", "subject_name"], as_list=True))
	for r in frappe.get_all("CBC Progress Report", filters={"student": student, "status": "Published"},
							fields=["name", "school_term", "published_on", "strengths", "areas_to_improve", "class_teacher_remark"],
							order_by="published_on desc", limit=4):
		areas = frappe.get_all("CBC Progress Area", filters={"parent": r.name, "parenttype": "CBC Progress Report"},
							   fields=["subject", "level", "descriptor", "teacher_comment"], order_by="idx")
		out.append({**r, "term": frappe.db.get_value("School Term", r.school_term, "term_name") or r.school_term,
					"date": formatdate(r.published_on, "d MMM yyyy"),
					"url": f"/api/method/school_erp.api.cbc.download_progress_report?name={r.name}",
					"areas": [{**a, "subject_name": names.get(a.subject, a.subject)} for a in areas]})
	return out
