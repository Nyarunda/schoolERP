"""One-click school setup from School Settings. Safe to run more than once: it only creates what is missing."""

from datetime import date

import frappe
from frappe import _

from school_erp.setup.install import make_custom_fields, make_customer_group, make_roles

CLASS_SETS = {
	"CBC (PP1 - Grade 9)": ["PP1", "PP2"] + [f"Grade {i}" for i in range(1, 10)],
	"8-4-4 (Form 1 - 4)": [f"Form {i}" for i in range(1, 5)],
	"British (Year 1 - 13)": ["Reception"] + [f"Year {i}" for i in range(1, 14)],
	"Custom": [],
}

# name, category, basis, priority, discountable
FEE_TYPES = [
	("Tuition", "Tuition", "Per Term", 1, 1),
	("Boarding", "Boarding", "Per Term", 2, 1),
	("Lunch", "Lunch", "Per Term", 3, 0),
	("Transport", "Transport", "Per Term", 4, 0),
	("Games & Activities", "Activity", "Per Term", 5, 0),
	("Exam Fee", "Exam", "Per Term", 6, 0),
	("Development Levy", "Other", "Per Term", 7, 0),
	("Admission Fee", "Admission", "Once", 8, 0),
]

PERIODS = [
	("P1", 1, "08:00", "08:40", 0), ("P2", 2, "08:40", "09:20", 0), ("Short Break", 3, "09:20", "09:30", 1),
	("P3", 4, "09:30", "10:10", 0), ("P4", 5, "10:10", "10:50", 0), ("Tea Break", 6, "10:50", "11:20", 1),
	("P5", 7, "11:20", "12:00", 0), ("P6", 8, "12:00", "12:40", 0), ("Lunch Break", 9, "12:40", "14:00", 1),
	("P7", 10, "14:00", "14:40", 0), ("P8", 11, "14:40", "15:20", 0),
]

SUBJECTS = [
	("Mathematics", "MATH"), ("English", "ENG"), ("Kiswahili", "KIS"), ("Science & Technology", "SCI"),
	("Social Studies", "SST"), ("Religious Education", "RE"), ("Creative Arts", "ART"), ("Physical Education", "PE"),
]


LEAVE_TYPES = [
	("Annual Leave", 21, {"requires_reliever": 1}),
	("Sick Leave", 14, {"requires_attachment": 1}),
	("Maternity Leave", 90, {"gender": "Female", "include_weekends": 1, "requires_reliever": 1}),
	("Paternity Leave", 14, {"gender": "Male", "include_weekends": 1}),
	("Compassionate Leave", 5, {}),
	("Study Leave", 10, {"requires_reliever": 1}),
	("Unpaid Leave", 0, {"is_paid": 0}),
]

# category, candidate account names (first one found in the chart of accounts wins)
EXPENSE_CATEGORIES = [
	("Fuel & Transport", ["Fuel", "Travel Expenses", "Miscellaneous Expenses"]),
	("Vehicle Repairs", ["Repairs and Maintenance", "Miscellaneous Expenses"]),
	("Food & Kitchen", ["Cost of Goods Sold", "Miscellaneous Expenses"]),
	("Stationery & Teaching Materials", ["Office Supplies", "Print and Stationery", "Miscellaneous Expenses"]),
	("Utilities (Water & Electricity)", ["Utility Expenses", "Miscellaneous Expenses"]),
	("Repairs & Maintenance", ["Repairs and Maintenance", "Miscellaneous Expenses"]),
	("Casual Labour", ["Salary", "Miscellaneous Expenses"]),
	("Sports & Activities", ["Entertainment Expenses", "Miscellaneous Expenses"]),
	("Office & Admin", ["Office Maintenance Expenses", "Administrative Expenses", "Miscellaneous Expenses"]),
]


def _find_expense_account(company, names):
	for n in names:
		acc = frappe.db.get_value("Account", {"company": company, "account_name": n, "is_group": 0})
		if acc:
			return acc
	return frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0})


def _ensure(doctype, name, values):
	if frappe.db.exists(doctype, name):
		return False
	frappe.get_doc(dict(doctype=doctype, **values)).insert(ignore_permissions=True)
	return True


@frappe.whitelist()
def run_setup():
	frappe.only_for(["System Manager", "School Admin"])
	settings = frappe.get_doc("School Settings")
	if not settings.company:
		frappe.throw(_("Choose the Company on School Settings first"))

	created = []
	make_roles()
	make_custom_fields()
	make_customer_group()

	# no cash rounding on fee invoices: statements must add up to the shilling
	frappe.db.set_single_value("Global Defaults", "disable_rounded_total", 1)

	if not settings.default_income_account:
		settings.default_income_account = frappe.db.get_value("Company", settings.company, "default_income_account")
	if not settings.cost_center:
		settings.cost_center = frappe.db.get_value("Company", settings.company, "cost_center")
	if not settings.customer_group:
		settings.customer_group = "Students"

	# classes
	for i, cls in enumerate(CLASS_SETS.get(settings.education_system, []), 1):
		if _ensure("School Class", cls, {"class_name": cls, "level": i, "is_active": 1}):
			created.append(cls)
	classes = CLASS_SETS.get(settings.education_system, [])
	for a, b in zip(classes, classes[1:]):
		frappe.db.set_value("School Class", a, "next_class", b)

	from school_erp import licensing

	# fee types (+ their service items)
	for name, cat, basis, prio, disc in (FEE_TYPES if licensing.is_enabled("fees") else []):
		if _ensure("Fee Type", name, {"fee_type_name": name, "category": cat, "charge_basis": basis, "priority": prio, "discountable": disc}):
			created.append(name)

	# timetable masters only if licensed
	if licensing.is_enabled("timetable"):
		for name, seq, start, end, brk in PERIODS:
			_ensure("Period", name, {"period_name": name, "sequence": seq, "start_time": start, "end_time": end, "is_break": brk})
		for name, short in SUBJECTS:
			_ensure("Subject", name, {"subject_name": name, "short_name": short, "subject_code": short})

	# staff: standard leave types
	if licensing.is_enabled("staff"):
		for name, days, extra in LEAVE_TYPES:
			if _ensure("Leave Type", name, {"leave_type_name": name, "days_per_year": days, **extra}):
				created.append(name)

	# expenses: categories mapped to the company's expense accounts
	if licensing.is_enabled("expenses"):
		for cat, account_names in EXPENSE_CATEGORIES:
			acc = _find_expense_account(settings.company, account_names)
			if acc and _ensure("Expense Category", cat, {"category_name": cat, "expense_account": acc, "is_active": 1}):
				created.append(cat)

	# exams: grading scales (CBC, KCSE) and a default matching the education system
	if licensing.is_enabled("exams"):
		from school_erp.api.exams import install_default_scales

		install_default_scales()
		if not settings.default_grading_scale:
			settings.default_grading_scale = "KCSE (8-4-4)" if settings.education_system.startswith("8-4-4") else "CBC"

	# current year + three terms
	year = str(date.today().year)
	if _ensure("School Year", year, {"year_name": year, "start_date": f"{year}-01-01", "end_date": f"{year}-12-31", "is_current": 1}):
		created.append(year)
	terms = [("Term 1", "01-06", "04-04"), ("Term 2", "04-28", "08-01"), ("Term 3", "08-25", "10-31")]
	for term, start, end in terms:
		_ensure("School Term", f"{term} {year}",
				{"term_name": term, "school_year": year, "start_date": f"{year}-{start}", "end_date": f"{year}-{end}"})

	# M-Pesa as a payment mode (account must be set by the accountant)
	if not frappe.db.exists("Mode of Payment", "M-Pesa"):
		frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "M-Pesa", "type": "Phone", "enabled": 1}).insert(ignore_permissions=True)
		created.append("M-Pesa")
	if not settings.default_mode_of_payment:
		settings.default_mode_of_payment = "M-Pesa"
	if not settings.mpesa_mode_of_payment:
		settings.mpesa_mode_of_payment = "M-Pesa"

	from school_erp.setup.workflows import make_workflows, sync_leave_approvers

	make_workflows()
	sync_leave_approvers()
	settings.setup_complete = 1
	settings.save()
	return {
		"created": created,
		"next_steps": [
			"Set the bank/M-Pesa account on Mode of Payment 'M-Pesa' for your company",
			"Adjust term dates under School Term",
			"Create Streams for each class",
			"Create a School Fee Structure for the term",
		],
	}
