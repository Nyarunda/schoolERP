"""Library: issuing and returning copies, renewals, lost books, fines billed to the fee account, overdue SMS."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, getdate, nowdate

from school_erp import licensing
from school_erp.logic.library import copy_counts, days_overdue, due_date_for, fine_for, reminder_due, renew_problem

FINE_FEE_TYPE = "Library Fine"


def library_settings():
	from school_erp.api.singles import get_settings

	return get_settings("Library Settings")


def set_copy_status(book, accession_no, status, condition=None):
	values = {"status": status}
	if condition:
		values["condition"] = condition
	frappe.db.set_value("Library Book Copy", {"parent": book, "parenttype": "Library Book", "accession_no": accession_no}, values)
	statuses = frappe.get_all("Library Book Copy", filters={"parent": book, "parenttype": "Library Book"}, pluck="status")
	c = copy_counts(statuses)
	frappe.db.set_value("Library Book", book, {"total_copies": c["total"], "available_copies": c["available"]}, update_modified=False)


@frappe.whitelist()
def available_copies(book):
	licensing.require("library")
	frappe.has_permission("Library Book", "read", throw=True)
	return frappe.get_all("Library Book Copy", filters={"parent": book, "parenttype": "Library Book", "status": "Available"},
						  pluck="accession_no", order_by="idx")


def _loan(name):
	licensing.require("library")
	doc = frappe.get_doc("Library Loan", name)
	frappe.has_permission("Library Loan", "write", doc, throw=True)
	return doc


@frappe.whitelist(methods=["POST"])
def return_book(name, condition="Good"):
	doc = _loan(name)
	if doc.status != "On Loan":
		frappe.throw(_("This book is already {0}").format(doc.status.lower()))
	s = library_settings()
	today = getdate(nowdate())
	late = days_overdue(doc.due_date, today)
	fine = fine_for(late, s.fine_per_day, s.fine_grace_days, s.max_fine)
	doc.db_set({"status": "Returned", "return_date": today, "days_overdue": late, "fine_amount": fine})
	set_copy_status(doc.book, doc.accession_no, "Damaged" if condition == "Damaged" else "Available",
					None if condition == "Damaged" else condition)
	msg = _("Returned {0} day(s) late. Fine: {1}").format(late, frappe.utils.fmt_money(fine)) if fine else None
	if fine and doc.student and cint(s.bill_fines_to_fees) and licensing.is_enabled("fees"):
		inv = bill_fine(name)
		msg = _("{0}. Billed on invoice {1}.").format(msg, inv["invoice"])
	return {"fine": fine, "message": msg}


@frappe.whitelist(methods=["POST"])
def renew_loan(name):
	doc = _loan(name)
	s = library_settings()
	problem = renew_problem(doc.status, doc.due_date, getdate(nowdate()), doc.renewals, s.max_renewals)
	if problem:
		frappe.throw(_(problem))
	days = s.loan_days_student if doc.borrower_type == "Student" else s.loan_days_teacher
	new_due = due_date_for(max(getdate(doc.due_date), getdate(nowdate())), days)
	doc.db_set({"due_date": new_due, "renewals": cint(doc.renewals) + 1})
	return {"due_date": str(new_due), "message": _("Renewed until {0}").format(formatdate(new_due, "d MMM yyyy"))}


@frappe.whitelist(methods=["POST"])
def mark_lost(name):
	doc = _loan(name)
	if doc.status != "On Loan":
		frappe.throw(_("Only a book that is out can be marked lost"))
	s = library_settings()
	late = days_overdue(doc.due_date, nowdate())
	charge = flt(frappe.db.get_value("Library Book", doc.book, "price")) + fine_for(late, s.fine_per_day, s.fine_grace_days, s.max_fine)
	doc.db_set({"status": "Lost", "return_date": nowdate(), "days_overdue": late, "fine_amount": charge})
	set_copy_status(doc.book, doc.accession_no, "Lost")
	if charge and doc.student and cint(s.bill_fines_to_fees) and licensing.is_enabled("fees"):
		bill_fine(name)
	return {"fine": charge}


def ensure_fine_fee_type():
	if not frappe.db.exists("Fee Type", FINE_FEE_TYPE):
		frappe.get_doc({"doctype": "Fee Type", "fee_type_name": FINE_FEE_TYPE, "category": "Other", "charge_basis": "Per Term",
						"priority": 20, "discountable": 0, "description": "Library fines and lost-book charges"}).insert(ignore_permissions=True)
	return FINE_FEE_TYPE


@frappe.whitelist(methods=["POST"])
def bill_fine(name):
	"""Invoice a learner's fine (or lost-book charge) to their fee account, once."""
	doc = _loan(name)
	licensing.require("fees")
	if doc.fine_invoice:
		return {"invoice": doc.fine_invoice, "existing": True}
	if not doc.student or flt(doc.fine_amount) <= 0 or doc.fine_waived:
		frappe.throw(_("There is no fine to bill"))
	from school_erp.api.billing import _fee_types, make_invoice

	ensure_fine_fee_type()
	what = _("Lost book") if doc.status == "Lost" else _("Late return, {0} day(s)").format(doc.days_overdue)
	line = {"fee_type": FINE_FEE_TYPE, "amount": flt(doc.fine_amount), "discount_percent": 0,
			"description": f"{what}: {doc.book_title} ({doc.accession_no})"}
	student = frappe.get_doc("Student", doc.student)
	# No term on the invoice: term billing skips a learner who already has an invoice for the term, and a fine must
	# never stop the learner's fees from being billed.
	si = make_invoice(student, None, [line], _fee_types(), nowdate(), add_days(nowdate(), 14),
					  remarks=f"{_('Library fine')} - {student.student_name} ({student.name}): {line['description']}")
	doc.db_set("fine_invoice", si.name)
	return {"invoice": si.name}


def remind_overdue():
	"""Daily: SMS the parents of learners with overdue books, the day after the due date and then weekly."""
	if not licensing.is_enabled("library") or not licensing.is_enabled("messaging"):
		return
	s = library_settings()
	if not cint(s.sms_overdue):
		return
	from school_erp.api.messaging import sms_student

	today = getdate(nowdate())
	school = frappe.db.get_single_value("School Settings", "school_name") or ""
	for loan in frappe.get_all("Library Loan", filters={"status": "On Loan", "borrower_type": "Student", "due_date": ("<", today)},
							   fields=["name", "student", "book_title", "due_date", "last_reminder"]):
		late = days_overdue(loan.due_date, today)
		if not reminder_due(late, loan.last_reminder, today):
			continue
		try:
			student = frappe.get_doc("Student", loan.student)
			sms_student(student, "Dear {guardian_name}, {student_name} has an overdue library book: " + (loan.book_title or "")[:50]
						+ ", due " + formatdate(loan.due_date, "d MMM") + ". Please return it. - " + school,
						{"student_name": student.first_name})
		except Exception:
			frappe.log_error(title=f"Library reminder failed: {loan.name}")
		frappe.db.set_value("Library Loan", loan.name, "last_reminder", today, update_modified=False)
		frappe.db.commit()
