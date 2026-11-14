"""Term billing: one Sales Invoice per student per term."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from school_erp import licensing
import json

from school_erp.logic.billing import compute_fee_lines, describe_lines, net_amount, summarize_run


def _fee_types():
	rows = frappe.get_all(
		"Fee Type", fields=["name", "category", "charge_basis", "priority", "discountable", "item", "income_account", "vat_treatment"]
	)
	return {r.name: r for r in rows}


def _structures(term):
	out = []
	for s in frappe.get_all(
		"School Fee Structure", filters={"school_term": term, "is_active": 1}, fields=["name", "school_class", "boarding_type"]
	):
		s["items"] = frappe.get_all(
			"Fee Structure Item", filters={"parent": s.name}, fields=["fee_type", "amount", "description"], order_by="idx"
		)
		out.append(s)
	return out


def _routes():
	if not licensing.is_enabled("transport"):
		return {}
	return {r.name: r for r in frappe.get_all("Transport Route", fields=["name", "fee_per_term", "fee_type", "is_active"])}


def _activities():
	if not licensing.is_enabled("activities"):
		return {}
	return {r.name: r for r in frappe.get_all("School Activity", fields=["name", "fee_per_term", "fee_type", "is_active"])}


def _once_billed(student, fee_types):
	once = [k for k, v in fee_types.items() if v.charge_basis == "Once"]
	if not once:
		return set()
	rows = frappe.db.sql(
		"""select distinct sii.fee_type from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.student = %s and si.docstatus = 1 and si.is_return = 0 and sii.fee_type in %s""",
		(student, tuple(once)),
	)
	return {r[0] for r in rows}


def student_context(doc):
	return {
		"school_class": doc.school_class,
		"boarding_type": doc.boarding_type,
		"takes_lunch": doc.takes_lunch,
		"transport_route": doc.transport_route,
		"activities": [a.activity for a in doc.activities],
		"scholarship_percent": doc.scholarship_percent,
	}


class BillingData:
	"""Loads masters once per run."""

	def __init__(self, term):
		self.term = term
		self.fee_types = _fee_types()
		self.structures = _structures(term)
		self.routes = _routes()
		self.activities = _activities()
		self.modules = licensing.get_state()["modules"]

	def lines_for(self, student_doc):
		return compute_fee_lines(
			student_context(student_doc),
			self.structures,
			self.fee_types,
			self.routes,
			self.activities,
			self.modules,
			_once_billed(student_doc.name, self.fee_types),
		)


def existing_invoice(student, term):
	return frappe.db.get_value(
		"Sales Invoice", {"student": student, "school_term": term, "docstatus": ("<", 2), "is_return": 0}
	)


def make_invoice(student_doc, term, lines, fee_types, posting_date, due_date, run=None, submit=True, remarks=None):
	settings = frappe.get_cached_doc("School Settings")
	si = frappe.new_doc("Sales Invoice")
	si.company = settings.company
	si.customer = student_doc.customer or student_doc.name
	si.student = student_doc.name
	si.school_term = term
	si.fee_billing_run = run
	si.set_posting_time = 1
	si.posting_date = posting_date
	si.due_date = due_date
	si.disable_rounded_total = 1
	si.ignore_pricing_rule = 1
	si.remarks = remarks or f"{term or _('School')} fees - {student_doc.student_name} ({student_doc.name})"
	for line in lines:
		ft = fee_types[line["fee_type"]]
		row = {
			"item_code": ft.item,
			"item_name": line["fee_type"],
			"description": line["description"],
			"fee_type": line["fee_type"],
			"qty": 1,
			"uom": "Nos",
			"price_list_rate": line["amount"],
			"rate": net_amount(line),
			"discount_percentage": line["discount_percent"] or 0,
		}
		income = ft.income_account or settings.default_income_account
		if income:
			row["income_account"] = income
		if settings.cost_center:
			row["cost_center"] = settings.cost_center
		si.append("items", row)
	from school_erp.api import tax

	tax.apply_vat(si, settings, fee_types)  # only for a VAT-registered school
	si.flags.ignore_permissions = True
	si.insert()
	if submit:
		si.submit()
	return si


def students_for(f):
	"""Active students matching a run's filters: classes (list), stream, boarding_type."""
	filters = {"status": "Active"}
	classes = [c for c in (f.get("classes") or ([f["school_class"]] if f.get("school_class") else [])) if c]
	if classes:
		filters["school_class"] = ("in", classes)
	if f.get("stream"):
		filters["stream"] = f["stream"]
	if f.get("boarding_type") and f["boarding_type"] != "All":
		filters["boarding_type"] = f["boarding_type"]
	return frappe.get_all("Student", filters=filters, pluck="name", order_by="school_class, stream, student_name")


def run_filters(doc):
	return {"classes": [c.school_class for c in doc.get("classes") or []], "stream": doc.stream, "boarding_type": doc.boarding_type}


def fill_run(doc):
	"""Work out every matching student's fee lines and put them on the run for review."""
	licensing.require("fees")
	data = BillingData(doc.school_term)
	currency = frappe.db.get_single_value("School Settings", "currency")
	fmt = lambda v: frappe.utils.fmt_money(v, precision=0, currency=None)  # noqa: E731
	doc.set("students", [])
	already = no_fees = 0
	for name in students_for(run_filters(doc)):
		if existing_invoice(name, doc.school_term):
			already += 1
			continue
		stu = frappe.get_cached_doc("Student", name)
		lines = data.lines_for(stu)
		if not lines:
			no_fees += 1
			continue
		doc.append("students", {
			"include": 1, "student": name, "student_name": stu.student_name, "stream": stu.stream, "school_class": stu.school_class,
			"fee_lines": describe_lines(lines, fmt), "total": sum(net_amount(l) for l in lines),
			"lines_json": json.dumps(lines), "status": "Pending",
		})
	doc.already_billed = already
	doc.no_fees = no_fees
	doc.fetched_on = frappe.utils.now_datetime()
	set_run_totals(doc)
	return doc


def set_run_totals(doc):
	rows = [{"include": r.include, "lines": json.loads(r.lines_json or "[]")} for r in doc.students]
	summary = summarize_run(rows)
	doc.total_students = summary["students"]
	doc.total_amount = summary["amount"]
	doc.set("fee_summary", [{"fee_type": r["fee_type"], "students": r["students"], "amount": r["amount"]} for r in summary["by_fee_type"]])


@frappe.whitelist()
def bill_single_student(student, school_term, posting_date=None, due_date=None):
	"""Bill one student for a term (e.g. a mid-term admission)."""
	frappe.has_permission("Sales Invoice", "create", throw=True)
	licensing.require("fees", "Fee Billing Run")
	if existing_invoice(student, school_term):
		frappe.throw(_("{0} has already been billed for {1}").format(student, school_term))
	term = frappe.get_cached_doc("School Term", school_term)
	data = BillingData(school_term)
	doc = frappe.get_doc("Student", student)
	lines = data.lines_for(doc)
	if not lines:
		frappe.throw(_("No fees apply to {0} for {1}. Check the fee structure.").format(doc.student_name, school_term))
	posting_date = getdate(posting_date or frappe.utils.nowdate())
	# a mid-term admission is billed after the term started: never due before it is posted
	due_date = getdate(due_date) if due_date else max(getdate(term.start_date), posting_date)
	if due_date < posting_date:
		frappe.throw(_("Due Date cannot be before the posting date"))
	si = make_invoice(doc, school_term, lines, data.fee_types, posting_date, due_date, submit=True)
	return si.name


def execute_billing_run(run):
	"""Background job started when a Fee Billing Run is posted: invoices exactly the reviewed, ticked rows."""
	doc = frappe.get_doc("Fee Billing Run", run)
	doc.db_set("status", "Running", commit=True)
	errors, created, skipped, total = [], 0, 0, 0.0
	invoiced_students = []
	try:
		fee_types = BillingData(doc.school_term).fee_types
		for row in doc.students:
			if not row.include or row.status == "Invoiced":
				continue
			if existing_invoice(row.student, doc.school_term):
				frappe.db.set_value("Fee Billing Run Student", row.name, {"status": "Skipped", "note": _("Already invoiced for this term")})
				skipped += 1
				continue
			try:
				lines = json.loads(row.lines_json or "[]")
				student = frappe.get_doc("Student", row.student)
				si = make_invoice(student, doc.school_term, lines, fee_types, doc.posting_date, doc.due_date,
								  run=doc.name, submit=doc.submit_invoices)
				frappe.db.set_value("Fee Billing Run Student", row.name, {"status": "Invoiced", "sales_invoice": si.name, "note": None})
				frappe.db.commit()  # one student at a time so a failure never undoes the others
				created += 1
				total += flt(si.grand_total)
				invoiced_students.append(row.student)
			except Exception as e:
				frappe.db.rollback()
				msg = str(e) or frappe.get_traceback(with_context=False).strip().splitlines()[-1]
				frappe.db.set_value("Fee Billing Run Student", row.name, {"status": "Error", "note": msg[:140]})
				frappe.db.commit()
				errors.append(f"{row.student}: {msg}")
	except Exception:
		frappe.db.rollback()
		errors.append(frappe.get_traceback())
		doc.db_set({"status": "Failed", "error_log": "\n".join(errors)}, commit=True)
		return

	doc.db_set(
		{
			"status": "Completed with Errors" if errors else "Completed",
			"invoices_created": created,
			"students_skipped": skipped,
			"total_billed": total,
			"error_log": "\n".join(errors) or None,
		},
		commit=True,
	)

	if doc.send_notifications and doc.submit_invoices and invoiced_students and licensing.is_enabled("messaging"):
		frappe.enqueue(
			"school_erp.api.messaging.notify_billing",
			queue="long",
			timeout=3600,
			term=doc.school_term,
			due_date=str(doc.due_date),
			students=invoiced_students,
			now=bool(frappe.flags.in_test),
		)
	frappe.publish_realtime("fee_billing_run_done", {"name": doc.name}, doctype="Fee Billing Run", docname=doc.name)


# ----------------------------------------------------------------------------- automatic term billing
AUTO_BILL_WINDOW_DAYS = 14  # a term is billed automatically only up to 2 weeks after it starts


def auto_bill_terms():
	"""Daily: when a term is about to start (per School Settings), create its billing run, and post it if set to."""
	s = frappe.get_cached_doc("School Settings")
	if not s.auto_bill_terms or not licensing.is_enabled("fees"):
		return
	from frappe.utils import add_days, cint, getdate, nowdate

	from school_erp.api.notify import notify, users_for_role

	today = getdate(nowdate())
	lead = cint(s.auto_bill_days_before)
	for term in frappe.get_all("School Term", filters={"end_date": (">=", today)}, fields=["name", "start_date"], order_by="start_date"):
		start = getdate(term.start_date)
		if add_days(start, -lead) > today:
			continue  # not yet
		if today > add_days(start, AUTO_BILL_WINDOW_DAYS):
			continue  # long-running term (e.g. auto-billing just switched on): leave it to the bursar
		if frappe.db.exists("Fee Billing Run", {"school_term": term.name, "docstatus": ("<", 2)}):
			continue  # already billed (by hand or automatically)
		bursars = users_for_role("Bursar") + ([s.head_teacher_user] if s.head_teacher_user else [])
		if not frappe.db.exists("School Fee Structure", {"school_term": term.name, "is_active": 1}):
			if str(s.auto_bill_warned_on or "") != str(today):
				frappe.db.set_single_value("School Settings", "auto_bill_warned_on", today)
				notify(_("Automatic billing for {0} is waiting for a fee structure").format(term.name),
					   _("Create the School Fee Structures for {0} (or copy them from last term); billing will run the next day.").format(term.name),
					   users=bursars)
			continue
		run = frappe.new_doc("Fee Billing Run")
		posting = max(start, today) if lead == 0 else start
		run.update({
			"school_term": term.name, "posting_date": posting,
			"due_date": max(getdate(add_days(start, cint(s.auto_bill_due_days) or 14)), getdate(posting)), "boarding_type": "All",
			"submit_invoices": 1, "send_notifications": int(s.auto_bill_notify_parents or 0), "auto_generated": 1,
		})
		fill_run(run)
		run.flags.ignore_permissions = True
		run.insert()
		money = frappe.utils.fmt_money(run.total_amount, currency=s.currency)
		if s.auto_bill_mode == "Post automatically" and run.total_students:
			run.submit()
			notify(_("{0} fees posted automatically: {1} students, {2}").format(term.name, run.total_students, money),
				   users=bursars, doc=run, sms=False)
		else:
			notify(_("{0} fee billing is ready for review: {1} students, {2}").format(term.name, run.total_students, money),
				   _("Open the billing run, check the students and totals, untick anyone to leave out, then click Post."),
				   users=bursars, doc=run)
		frappe.db.commit()


@frappe.whitelist()
def copy_fee_structures(from_term, to_term, increase_percent=0, round_to=0):
	"""Copy every active fee structure (each class / boarding type) from one term to another,
	optionally raising amounts by a percentage and rounding (e.g. to the nearest 50)."""
	frappe.has_permission("School Fee Structure", "create", throw=True)
	licensing.require("fees")
	if from_term == to_term:
		frappe.throw(_("Pick a different term to copy to"))
	pct, step = flt(increase_percent), flt(round_to)
	created, skipped = [], []
	for name in frappe.get_all("School Fee Structure", filters={"school_term": from_term, "is_active": 1}, pluck="name"):
		src = frappe.get_doc("School Fee Structure", name)
		if frappe.db.exists("School Fee Structure", {"school_term": to_term, "school_class": src.school_class or ("is", "not set"),
													  "boarding_type": src.boarding_type, "is_active": 1}):
			skipped.append(src.title)
			continue
		new = frappe.copy_doc(src)
		new.school_term = to_term
		for row in new.items:
			amt = flt(row.amount) * (1 + pct / 100)
			row.amount = round(amt / step) * step if step else round(amt, 2)
		new.insert()
		created.append(new.name)
	return {"created": created, "skipped": skipped}


@frappe.whitelist()
@licensing.licensed("School Fee Structure")
def fee_matrix(school_year):
	"""Total fees per class (rows) per term (columns) for a year, for the Fee Structure form/report."""
	terms = frappe.get_all("School Term", filters={"school_year": school_year}, order_by="start_date", pluck="name")
	classes = frappe.get_all("School Class", filters={"is_active": 1}, order_by="level", pluck="name")
	rows = []
	for cls in classes:
		row = {"school_class": cls}
		for t in terms:
			totals = frappe.db.sql(
				"""select boarding_type, sum(total_amount) from `tabSchool Fee Structure`
				where school_term=%s and is_active=1 and (school_class=%s or ifnull(school_class,'')='')
				group by boarding_type""", (t, cls))
			row[t] = {bt: flt(v) for bt, v in totals}
		rows.append(row)
	return {"terms": terms, "rows": rows}
