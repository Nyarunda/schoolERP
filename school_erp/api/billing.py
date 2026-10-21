"""Term billing: one Sales Invoice per student per term."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from school_erp import licensing
from school_erp.logic.billing import compute_fee_lines, net_amount


def _fee_types():
	rows = frappe.get_all(
		"Fee Type", fields=["name", "category", "charge_basis", "priority", "discountable", "item", "income_account"]
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


def make_invoice(student_doc, term, lines, fee_types, posting_date, due_date, run=None, submit=True):
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
	si.remarks = f"{term} fees - {student_doc.student_name} ({student_doc.name})"
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
	si.flags.ignore_permissions = True
	si.insert()
	if submit:
		si.submit()
	return si


def students_for(term_filters):
	filters = {"status": "Active"}
	if term_filters.get("school_class"):
		filters["school_class"] = term_filters["school_class"]
	if term_filters.get("stream"):
		filters["stream"] = term_filters["stream"]
	return frappe.get_all("Student", filters=filters, pluck="name", order_by="school_class, stream, student_name")


@frappe.whitelist()
def preview_billing(school_term, school_class=None, stream=None):
	"""What a billing run would do, without creating anything."""
	frappe.has_permission("Fee Billing Run", "create", throw=True)
	licensing.require("fees")
	data = BillingData(school_term)
	students = students_for({"school_class": school_class, "stream": stream})
	out = {"students": len(students), "to_bill": 0, "already_billed": 0, "no_fees": 0, "total": 0.0, "rows": []}
	for name in students:
		if existing_invoice(name, school_term):
			out["already_billed"] += 1
			continue
		doc = frappe.get_cached_doc("Student", name)
		lines = data.lines_for(doc)
		if not lines:
			out["no_fees"] += 1
			continue
		total = sum(net_amount(l) for l in lines)
		out["to_bill"] += 1
		out["total"] += total
		if len(out["rows"]) < 200:
			out["rows"].append(
				{
					"student": name,
					"student_name": doc.student_name,
					"school_class": doc.school_class,
					"total": total,
					"lines": [{"fee_type": l["fee_type"], "amount": net_amount(l)} for l in lines],
				}
			)
	return out


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
	"""Background job started when a Fee Billing Run is submitted."""
	doc = frappe.get_doc("Fee Billing Run", run)
	doc.db_set("status", "Running", commit=True)
	errors, created, skipped, total = [], 0, 0, 0.0
	invoices = []
	try:
		data = BillingData(doc.school_term)
		for name in students_for({"school_class": doc.school_class, "stream": doc.stream}):
			if existing_invoice(name, doc.school_term):
				skipped += 1
				continue
			try:
				student = frappe.get_doc("Student", name)
				lines = data.lines_for(student)
				if not lines:
					skipped += 1
					continue
				si = make_invoice(
					student, doc.school_term, lines, data.fee_types,
					doc.posting_date, doc.due_date, run=doc.name, submit=doc.submit_invoices,
				)
				frappe.db.commit()  # one student at a time so a failure never undoes the others
				created += 1
				total += flt(si.grand_total)
				invoices.append((name, si.name))
			except Exception:
				frappe.db.rollback()
				errors.append(f"{name}: {frappe.get_traceback(with_context=False).strip().splitlines()[-1]}")
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

	if doc.send_notifications and doc.submit_invoices and invoices and licensing.is_enabled("messaging"):
		frappe.enqueue(
			"school_erp.api.messaging.notify_billing",
			queue="long",
			timeout=3600,
			term=doc.school_term,
			due_date=str(doc.due_date),
			students=[s for s, _ in invoices],
		)
	frappe.publish_realtime("fee_billing_run_done", {"name": doc.name}, doctype="Fee Billing Run", docname=doc.name)
