"""Parent fee statements: data, HTML and PDF."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, fmt_money, get_url, getdate, nowdate

from school_erp.api.payments import customer_of, invoice_fee_lines
from school_erp.logic.statement import breakdown_rows, build_ledger, status_line
from school_erp.logic.text import render

TEMPLATE_BODY = "school_erp/templates/fee_statement/body.html"
TEMPLATE_PAGE = "school_erp/templates/fee_statement/page.html"


def _default_period(from_date, to_date):
	to_date = getdate(to_date or nowdate())
	if from_date:
		return getdate(from_date), to_date
	from school_erp.school.doctype.school_term.school_term import get_current_term

	term = get_current_term(to_date)
	if term:
		year_start = frappe.db.get_value("School Year", term.school_year, "start_date")
		return getdate(year_start or term.start_date), to_date
	return add_days(to_date, -365), to_date


def _describe(vouchers):
	"""Parent-friendly description for each ledger voucher."""
	si = [v["voucher_no"] for v in vouchers if v["voucher_type"] == "Sales Invoice"]
	pe = [v["voucher_no"] for v in vouchers if v["voucher_type"] == "Payment Entry"]
	je = [v["voucher_no"] for v in vouchers if v["voucher_type"] == "Journal Entry"]
	si_map = {
		r.name: r
		for r in frappe.get_all(
			"Sales Invoice", filters={"name": ("in", si or [""])}, fields=["name", "school_term", "is_return", "remarks"]
		)
	}
	pe_map = {
		r.name: r
		for r in frappe.get_all(
			"Payment Entry",
			filters={"name": ("in", pe or [""])},
			fields=["name", "mode_of_payment", "reference_no", "fee_payment", "payment_type"],
		)
	}
	je_map = {r.name: r for r in frappe.get_all("Journal Entry", filters={"name": ("in", je or [""])}, fields=["name", "user_remark"])}
	for v in vouchers:
		v["date_label"] = formatdate(v["date"], "d MMM yyyy")
		vt, vn = v["voucher_type"], v["voucher_no"]
		if vt == "Sales Invoice" and vn in si_map:
			r = si_map[vn]
			if r.is_return:
				v.update(details="Fee credit / reversal", kind="adjustment")
			else:
				v.update(details=f"{r.school_term} fees" if r.school_term else "Fees charged", kind="charge")
			v["reference"] = vn
		elif vt == "Payment Entry" and vn in pe_map:
			r = pe_map[vn]
			if r.payment_type == "Pay":
				v.update(details="Refund", kind="adjustment")
			else:
				v.update(details=f"Payment - {r.mode_of_payment or 'received'}", kind="payment")
			v["reference"] = r.reference_no if r.reference_no and r.reference_no != r.fee_payment else (r.fee_payment or vn)
		elif vt == "Journal Entry":
			r = je_map.get(vn)
			v.update(details=(r.user_remark if r and r.user_remark else "Adjustment")[:60], kind="adjustment", reference=vn)
		else:
			v.update(details=vt, kind="adjustment", reference=vn)
	return vouchers


def build_statement(student, from_date=None, to_date=None):
	frappe.has_permission("Student", "read", student, throw=True)
	settings = frappe.get_cached_doc("School Settings")
	stu = frappe.get_doc("Student", student)
	customer = customer_of(student)
	from_date, to_date = _default_period(from_date, to_date)
	currency = settings.currency or frappe.db.get_value("Company", settings.company, "default_currency")

	def money(v, with_currency=True):
		return fmt_money(flt(v), precision=2, currency=currency if with_currency else None)

	opening = flt(
		frappe.db.sql(
			"""select coalesce(sum(debit - credit), 0) from `tabGL Entry`
			where party_type='Customer' and party=%s and is_cancelled=0 and posting_date < %s""",
			(customer, from_date),
		)[0][0]
	)
	vouchers = frappe.db.sql(
		"""select posting_date as date, voucher_type, voucher_no, sum(debit) as debit, sum(credit) as credit, min(creation) as created
		from `tabGL Entry`
		where party_type='Customer' and party=%s and is_cancelled=0 and posting_date between %s and %s
		group by posting_date, voucher_type, voucher_no
		order by posting_date, created""",
		(customer, from_date, to_date),
		as_dict=True,
	)
	ledger = build_ledger(opening, _describe([dict(v) for v in vouchers]))

	# fee-type breakdown for invoices raised in the period
	period_invoices = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "is_return": 0, "posting_date": ("between", [from_date, to_date])},
		pluck="name",
	)
	lines = [l for d in invoice_fee_lines(period_invoices).values() for l in d["lines"]]
	arrears = flt(
		frappe.db.sql(
			"""select coalesce(sum(outstanding_amount), 0) from `tabSales Invoice`
			where customer=%s and docstatus=1 and is_return=0 and posting_date < %s and outstanding_amount > 0""",
			(customer, from_date),
		)[0][0]
	)
	unallocated = flt(
		frappe.db.sql(
			"""select coalesce(sum(unallocated_amount), 0) from `tabPayment Entry`
			where party_type='Customer' and party=%s and docstatus=1 and payment_type='Receive'""",
			customer,
		)[0][0]
	)
	breakdown = breakdown_rows(lines, arrears, unallocated)

	due = frappe.db.sql(
		"""select min(due_date) from `tabSales Invoice`
		where customer=%s and docstatus=1 and is_return=0 and outstanding_amount > 0""",
		customer,
	)[0][0]
	due_label = formatdate(due, "d MMM yyyy") if due else None

	ctx_text = {
		"student_id": stu.name,
		"student_name": stu.student_name,
		"paybill": settings.paybill_number or "",
		"school_name": settings.school_name or "",
	}
	accent = settings.statement_accent_color or "#1f6f5c"
	return {
		"school": {
			"name": settings.school_name,
			"motto": settings.motto,
			"logo": get_url(settings.school_logo) if settings.school_logo else None,
			"address": settings.address,
			"phone": settings.phone,
			"email": settings.email,
			"website": settings.website,
			"accent": accent,
		},
		"student": {
			"id": stu.name,
			"name": stu.student_name,
			"class": stu.school_class,
			"stream": stu.stream,
			"admission_number": stu.admission_number,
			"guardian": stu.primary_guardian,
			"phone": stu.primary_phone,
			"boarding_type": stu.boarding_type,
			"transport_route": stu.transport_route,
		},
		"period": {
			"from": formatdate(from_date, "d MMM yyyy"),
			"to": formatdate(to_date, "d MMM yyyy"),
			"generated": formatdate(nowdate(), "d MMM yyyy"),
		},
		"currency": currency,
		"ledger": ledger,
		"breakdown": breakdown if settings.show_fee_breakdown else None,
		"status": status_line(ledger["closing"], due_label, money),
		"due_date": due_label,
		"payment_instructions": render(settings.payment_instructions or "", ctx_text),
		"paybill": settings.paybill_number,
		"bank_details": settings.bank_details,
		"footer": settings.statement_footer,
		"money": money,
	}


@frappe.whitelist()
def get_statement_data(student, from_date=None, to_date=None):
	"""JSON-safe statement numbers (for the desk UI or a parent portal)."""
	data = build_statement(student, from_date, to_date)
	data.pop("money", None)
	return data


def render_fee_statement(student, from_date=None, to_date=None, full_page=False):
	"""Used by the 'Fee Statement' print format and for PDFs."""
	data = build_statement(student, from_date, to_date)
	html = frappe.render_template(TEMPLATE_BODY, {"s": data})
	if full_page:
		html = frappe.render_template(TEMPLATE_PAGE, {"body": html, "title": f"Fee Statement {student}"})
	return html


def statement_pdf(student, from_date=None, to_date=None):
	from frappe.utils.pdf import get_pdf

	html = render_fee_statement(student, from_date, to_date, full_page=True)
	return get_pdf(html, {"page-size": "A4", "margin-top": "10mm", "margin-bottom": "10mm", "margin-left": "10mm", "margin-right": "10mm"})


@frappe.whitelist()
def download_statement(student, from_date=None, to_date=None):
	frappe.has_permission("Student", "read", student, throw=True)
	frappe.local.response.filename = f"Fee Statement {student}.pdf"
	frappe.local.response.filecontent = statement_pdf(student, from_date, to_date)
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def get_balance(student):
	from school_erp.api.payments import party_balance

	frappe.has_permission("Student", "read", student, throw=True)
	return party_balance(student)
