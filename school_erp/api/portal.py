"""Parent portal: logins for guardians, and everything a parent may see about their own children."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, formatdate, get_url, getdate, nowdate, random_string, strip_html

from school_erp import licensing
from school_erp.logic.paybill import is_till
from school_erp.logic.text import normalize_phone, render

PARENT_ROLE = "Parent"


# ----------------------------------------------------------------------------- access
def children_of(user=None) -> list[str]:
	user = user or frappe.session.user
	if user in ("Guest", None):
		return []
	return frappe.db.sql_list(
		"""select distinct g.parent from `tabStudent Guardian` g join `tabStudent` s on s.name = g.parent
		where g.parenttype='Student' and g.user=%s and s.status in ('Active', 'Suspended') order by s.student_name""", user)


def payer_phone(student=None, user=None) -> str:
	"""The number to prefill for an M-Pesa prompt, in the local form parents type (07..): this parent's own number
	on the child's guardian row, else any of their guardian rows, else their login's mobile."""
	user = user or frappe.session.user
	filters = {"parenttype": "Student", "user": user, "mobile_no": ("is", "set")}
	if student:
		filters["parent"] = student
	mobile = frappe.db.get_value("Student Guardian", filters, "mobile_no") or (
		student and payer_phone(None, user)) or frappe.db.get_value("User", user, "mobile_no") or ""
	cc = frappe.db.get_single_value("School Settings", "country_code") or "254"
	full = normalize_phone(mobile, cc) if mobile else None
	return ("0" + full[len(cc):]) if full and full.startswith(cc) else (mobile or "")


def assert_parent_of(student):
	if student not in children_of():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _require_portal():
	if not licensing.is_enabled("portal") or not frappe.db.get_single_value("School Settings", "portal_enabled"):
		frappe.throw(_("The parent portal is not available"), frappe.PermissionError)


# ----------------------------------------------------------------------------- creating parent logins
def _login_email(guardian, cc):
	if guardian.email:
		return guardian.email.strip().lower()
	phone = normalize_phone(guardian.mobile_no, cc)
	return f"{phone}@parents.invalid" if phone else None


def ensure_parent_user(guardian, cc) -> tuple[str | None, str | None]:
	"""Create (or reuse) a website login for a guardian. Returns (user, new_password or None)."""
	email = _login_email(guardian, cc)
	if not email:
		return None, None
	mobile = normalize_phone(guardian.mobile_no, cc)
	# Frappe matches the login exactly: mobile_no in the local form parents type (0712...), username in international form (2547...)
	local = ("0" + mobile[len(cc):]) if mobile and cc and mobile.startswith(cc) else mobile
	existing = frappe.db.get_value("User", email) or (mobile and frappe.db.get_value(
		"User", {"mobile_no": ("in", [local, mobile, "+" + mobile, guardian.mobile_no])}))
	password = None
	if existing:
		user = frappe.get_doc("User", existing)
	else:
		first, _sp, last = (guardian.guardian_name or "Parent").partition(" ")
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": first, "last_name": last, "mobile_no": local,
			"username": mobile if mobile and not frappe.db.exists("User", {"username": mobile}) else None,
			"send_welcome_email": 0, "user_type": "Website User", "enabled": 1,
		})
		user.flags.ignore_permissions = True
		user.insert()
		password = random_string(8)
		from frappe.utils.password import update_password

		update_password(user.name, password)
	if PARENT_ROLE not in frappe.get_roles(user.name):
		user.flags.ignore_permissions = True
		user.add_roles(PARENT_ROLE)
	return user.name, password


@frappe.whitelist()
def give_portal_access(student=None, all_students=0, send_sms=1):
	"""Create portal logins for guardians of one student, or of every active student. SMSes new logins their password."""
	_require_portal()
	frappe.has_permission("Student", "write", throw=True)
	s = frappe.get_cached_doc("School Settings")
	frappe.db.set_single_value("System Settings", "allow_login_using_mobile_number", 1)
	frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)
	names = [student] if student else frappe.get_all("Student", filters={"status": "Active"}, pluck="name") if int(all_students) else []
	created, linked, no_contact, messages = 0, 0, 0, []
	for name in names:
		doc = frappe.get_doc("Student", name)
		changed = False
		for g in doc.guardians:
			if not (g.mobile_no or g.email):
				no_contact += 1
				continue
			user, password = ensure_parent_user(g, s.country_code)
			if not user:
				no_contact += 1
				continue
			if g.user != user:
				g.user = user
				changed = True
				linked += 1
			if password:
				created += 1
				messages.append((g, user, password))
		if changed:
			doc.flags.ignore_permissions = True
			doc.save()
	if int(send_sms) and messages and licensing.is_enabled("messaging"):
		from school_erp.api.messaging import send_sms as sms

		for g, user, password in messages:
			kids = ", ".join(frappe.db.get_value("Student", c, "first_name") for c in children_of(user))
			login = normalize_phone(g.mobile_no, s.country_code) or user
			text = render(s.portal_welcome_sms, {"name": (g.guardian_name or "Parent").split(" ")[0], "students": kids,
												 "url": get_url("/login"), "login": "0" + login[3:] if login.startswith("254") else login,
												 "password": password, "school_name": s.school_name or ""})
			if g.mobile_no:
				sms([g.mobile_no], text)
	return {"new_logins": created, "linked": linked, "without_contact": no_contact,
			"passwords": [{"guardian": g.guardian_name, "login": u, "password": p} for g, u, p in messages][:50]}


# ----------------------------------------------------------------------------- what parents see
def child_summary(student):
	from school_erp.api.payments import party_balance

	stu = frappe.get_doc("Student", student)
	balance = party_balance(student)
	due = frappe.db.sql("""select min(due_date) from `tabSales Invoice`
		where customer=%s and docstatus=1 and is_return=0 and outstanding_amount>0""", stu.customer or student)[0][0]
	payments = frappe.get_all("Fee Payment", filters={"student": student, "docstatus": 1},
							  fields=["name", "posting_date", "amount", "mode_of_payment", "reference_no"], order_by="posting_date desc", limit=5)
	for p in payments:
		p["date"] = formatdate(p.posting_date, "d MMM yyyy")
	cards = []
	if licensing.is_enabled("exams"):
		cards = frappe.get_all("Report Card", filters={"student": student, "status": "Published"},
							   fields=["name", "exam", "mean_grade", "mean_percent", "stream_position", "stream_size", "published_on"],
							   order_by="published_on desc", limit=6)
		for r in cards:
			r["exam_name"] = frappe.db.get_value("Exam", r.exam, "exam_name")
	from school_erp.api.attendance import student_attendance
	from school_erp.school.doctype.school_term.school_term import get_current_term

	term = get_current_term()
	attendance = student_attendance(student, term.start_date, term.end_date) if term else student_attendance(student)
	return {
		"attendance": attendance if attendance["marked"] else None, "term": term.name if term else None,
		"id": stu.name, "name": stu.student_name, "first_name": stu.first_name, "stream": stu.stream or stu.school_class,
		"photo": stu.photo, "balance": balance, "due": formatdate(due, "d MMM yyyy") if due else None,
		"payments": payments, "report_cards": cards, "payer_phone": payer_phone(student),
		"term_fees": term_fees(stu, term), "latest_results": latest_results(cards[0].name) if cards else None,
		"lessons": lessons(stu.stream, term), "concerns": my_concerns(student),
		"cbc_reports": cbc_reports(student),
	}


def cbc_reports(student):
	from school_erp.api.cbc import portal_reports

	return portal_reports(student)


def term_fees(stu, term):
	"""What this term's fees are for (by fee type) and how much of them is paid."""
	if not term:
		return None
	invoices = frappe.get_all("Sales Invoice", filters={"customer": stu.customer or stu.name, "docstatus": 1, "is_return": 0,
														 "school_term": term.name}, fields=["name", "grand_total", "outstanding_amount"])
	if not invoices:
		return None
	items = frappe.db.sql("""select coalesce(nullif(fee_type, ''), item_name) as fee, sum(amount) as amount
		from `tabSales Invoice Item` where parent in %s group by 1 order by sum(amount) desc""", [tuple(i.name for i in invoices)], as_dict=True)
	billed = flt(sum(i.grand_total for i in invoices))
	paid = billed - flt(sum(i.outstanding_amount for i in invoices))
	return {"term": term.term_name or term.name, "billed": billed, "paid": paid, "items": items,
			"percent": round(paid / billed * 100) if billed else 0}


def latest_results(report_card):
	"""The newest published report card, subject by subject, with the teachers' remarks."""
	rc = frappe.get_doc("Report Card", report_card)
	return {"exam": frappe.db.get_value("Exam", rc.exam, "exam_name") or rc.exam, "mean_grade": rc.mean_grade,
			"class_teacher_remark": rc.class_teacher_remark, "head_teacher_remark": rc.head_teacher_remark,
			"subjects": [{"subject": frappe.db.get_value("Subject", r.subject, "subject_name") or r.subject,
						  "percent": flt(r.percent, 1), "grade": r.grade, "remark": r.remark, "position": r.subject_position}
						 for r in rc.subjects]}


def lessons(stream, term):
	"""Today's lessons for the child's stream (the next school day's on a weekend)."""
	if not (stream and term and licensing.is_enabled("timetable")):
		return None
	tt = frappe.db.get_value("Timetable", {"stream": stream, "school_term": term.name})
	if not tt:
		return None
	day = getdate(nowdate())
	label = _("Today")
	if day.weekday() >= 5:
		label = _("Monday")
	name = "Monday" if day.weekday() >= 5 else day.strftime("%A")
	rows = frappe.get_all("Timetable Slot", filters={"parent": tt, "parenttype": "Timetable", "day": name},
						  fields=["period", "time", "subject", "teacher", "room"], order_by="idx")
	if not rows:
		return None
	for r in rows:
		r["subject_name"] = frappe.db.get_value("Subject", r.subject, "subject_name") or r.subject or ""
		r["teacher_name"] = frappe.db.get_value("Teacher", r.teacher, "teacher_name") if r.teacher else ""
	return {"label": label, "slots": rows}


# ----------------------------------------------------------------------------- concerns raised from the portal
CONCERN_CATEGORIES = ["Academics", "Fees & Payments", "Transport", "Meals", "Staff Conduct", "Bullying",
					  "Safety & Security", "Facilities", "Other"]


def my_concerns(student):
	if not licensing.is_enabled("welfare"):
		return None
	return [{"ref": r.name, "subject": r.subject, "status": r.status, "category": r.category,
			 "date": formatdate(r.creation, "d MMM yyyy"), "resolution": r.resolution if r.status in ("Resolved", "Closed") else None}
			for r in frappe.get_all("Complaint", filters={"student": student, "owner": frappe.session.user},
									fields=["name", "subject", "status", "category", "creation", "resolution"],
									order_by="creation desc", limit=5, ignore_permissions=True)]


@frappe.whitelist(methods=["POST"])
def raise_concern(student, category, subject, description):
	"""A parent tells the school about something: it becomes a Complaint the school follows up (Students & Welfare)."""
	_require_portal()
	assert_parent_of(student)
	licensing.require("welfare")
	if category not in CONCERN_CATEGORIES:
		frappe.throw(_("Choose what it is about"))
	subject, description = (subject or "").strip()[:140], (description or "").strip()[:3000]
	if len(subject) < 3 or len(description) < 10:
		frappe.throw(_("Write a short title and tell us what happened (at least a sentence)."))
	if frappe.db.count("Complaint", {"owner": frappe.session.user, "creation": (">", frappe.utils.add_to_date(None, hours=-24))}) >= 5:
		frappe.throw(_("You have raised several concerns today. Please call the school office."))
	user = frappe.session.user
	doc = frappe.get_doc({"doctype": "Complaint", "source": "Web Form", "relationship": "Parent / Guardian", "student": student,
						  "student_ref": student, "complainant_name": frappe.utils.get_fullname(user), "email": user if "@" in user else None,
						  "phone": payer_phone(student) or None, "category": category, "subject": subject, "description": description,
						  "status": "Open", "priority": "High" if category in ("Bullying", "Safety & Security") else "Medium"})
	doc.flags.ignore_permissions = True
	doc.insert()
	return {"ref": doc.name}


def parent_notices(students):
	classes = list({frappe.db.get_value("Student", s, "school_class") for s in students})
	rows = frappe.get_all("School Notice",
						  filters={"audience": "Parents", "publish_date": ("<=", nowdate()), "expiry_date": (">=", nowdate())},
						  fields=["name", "title", "message", "priority", "publish_date", "pinned", "parent_class"],
						  order_by="pinned desc, publish_date desc", limit=10)
	out = []
	for r in rows:
		if r.parent_class and r.parent_class not in classes:
			continue
		r["text"] = strip_html(r.message or "")
		r["date"] = formatdate(r.publish_date, "d MMM")
		r["new"] = date_diff(nowdate(), r.publish_date) <= 3
		out.append(r)
	return out


def portal_context():
	_require_portal()
	s = frappe.get_cached_doc("School Settings")
	kids = children_of()
	return {
		"school": {"name": s.school_name, "logo": s.school_logo, "accent": s.statement_accent_color or "#1f6f5c",
				   "paybill": s.paybill_number, "till": is_till(s.mpesa_account_type), "phone": s.phone},
		"currency": s.currency,
		"children": [child_summary(c) for c in kids],
		"notices": parent_notices(kids) if kids else [],
		"can_pay": bool(s.mpesa_enabled and s.mpesa_stk_enabled and licensing.is_enabled("mpesa")),
		"phone": payer_phone(),
		"parent_name": frappe.utils.get_fullname(frappe.session.user),
		"concern_categories": CONCERN_CATEGORIES if licensing.is_enabled("welfare") else [],
	}


# ----------------------------------------------------------------------------- parent actions
@frappe.whitelist()
def pay(student, amount, phone):
	_require_portal()
	assert_parent_of(student)
	from school_erp.api import stk

	name = stk.initiate(student, amount, phone, requested_by=frappe.session.user)
	return {"request": name}


@frappe.whitelist()
def payment_status(request):
	_require_portal()
	from school_erp.api import stk

	row = frappe.db.get_value("STK Push Request", request, ["student", "requested_by"], as_dict=True)
	if not row or (row.requested_by != frappe.session.user and row.student not in children_of()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	previous = frappe.session.user
	frappe.set_user("Administrator")  # querying Safaricom updates records the parent can't write
	try:
		st = stk.status(request)
	finally:
		frappe.set_user(previous)
	if not st:
		frappe.throw(_("Not found"))
	return {"status": st.status, "message": st.result_desc, "receipt": st.mpesa_receipt}


def _as_admin(fn, *args):
	previous = frappe.session.user
	frappe.set_user("Administrator")
	try:
		return fn(*args)
	finally:
		frappe.set_user(previous)


@frappe.whitelist()
def statement(student):
	_require_portal()
	assert_parent_of(student)
	from school_erp.api.statement import statement_pdf

	frappe.local.response.filename = f"Fee Statement {student}.pdf"
	frappe.local.response.filecontent = _as_admin(statement_pdf, student)
	frappe.local.response.type = "pdf"


@frappe.whitelist()
@licensing.licensed("Fee Payment")
def receipt(payment):
	_require_portal()
	student = frappe.db.get_value("Fee Payment", {"name": payment, "docstatus": 1}, "student")
	assert_parent_of(student)

	def make():
		from frappe.utils.pdf import get_pdf

		pf = frappe.get_doc("Print Format", "Fee Receipt")
		html = frappe.render_template(pf.html, {"doc": frappe.get_doc("Fee Payment", payment)})
		return get_pdf(f"<html><head><meta charset='utf-8'><style>{pf.css or ''}</style></head><body>{html}</body></html>")

	frappe.local.response.filename = f"Receipt {payment}.pdf"
	frappe.local.response.filecontent = _as_admin(make)
	frappe.local.response.type = "pdf"


@frappe.whitelist()
@licensing.licensed("Report Card")
def report_card(name):
	_require_portal()
	row = frappe.db.get_value("Report Card", name, ["student", "status"], as_dict=True)
	if not row or row.status != "Published":
		frappe.throw(_("Not available"), frappe.PermissionError)
	assert_parent_of(row.student)
	from school_erp.api.exams import report_card_pdf

	frappe.local.response.filename = f"Report Card {row.student}.pdf"
	frappe.local.response.filecontent = _as_admin(report_card_pdf, name)
	frappe.local.response.type = "pdf"
