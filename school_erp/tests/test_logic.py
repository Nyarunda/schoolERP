"""Framework-free tests: run with  pytest school_erp/tests/test_logic.py  (no bench needed)."""

from datetime import date
from functools import lru_cache

from school_erp.logic import license as lic
from school_erp.logic.allocation import allocate_payment, per_invoice_totals, split_invoice_paid
from school_erp.logic.billing import compute_fee_lines, net_amount
from school_erp.logic.statement import breakdown_rows, build_ledger
from school_erp.logic.text import normalize_phone, render
from school_erp.logic.timetable import find_duplicate_slots, find_teacher_clashes

ALL = ["core", "fees", "transport", "lunch", "activities", "messaging", "timetable"]

FEE_TYPES = {
	"Tuition": {"category": "Tuition", "charge_basis": "Per Term", "priority": 1, "discountable": 1},
	"Boarding": {"category": "Boarding", "charge_basis": "Per Term", "priority": 2, "discountable": 1},
	"Lunch": {"category": "Lunch", "charge_basis": "Per Term", "priority": 3, "discountable": 0},
	"Transport": {"category": "Transport", "charge_basis": "Per Term", "priority": 4, "discountable": 0},
	"Games & Activities": {"category": "Activity", "charge_basis": "Per Term", "priority": 5, "discountable": 0},
	"Admission Fee": {"category": "Admission", "charge_basis": "Once", "priority": 8, "discountable": 0},
}
STRUCTURES = [
	{"school_class": None, "boarding_type": "All", "items": [
		{"fee_type": "Tuition", "amount": 20000}, {"fee_type": "Lunch", "amount": 6000}, {"fee_type": "Admission Fee", "amount": 5000}]},
	{"school_class": "Grade 4", "boarding_type": "All", "items": [{"fee_type": "Tuition", "amount": 25000}]},
	{"school_class": None, "boarding_type": "Boarder", "items": [{"fee_type": "Boarding", "amount": 30000}]},
]
ROUTES = {"Route A": {"fee_per_term": 9000, "fee_type": "Transport", "is_active": 1}}
ACTS = {
	"Swimming": {"fee_per_term": 3000, "fee_type": "Games & Activities", "is_active": 1},
	"Chess": {"fee_per_term": 1000, "fee_type": "Games & Activities", "is_active": 1},
}


def student(**kw):
	base = {"school_class": "Grade 4", "boarding_type": "Day", "takes_lunch": 1, "transport_route": "Route A",
			"activities": ["Swimming", "Chess"], "scholarship_percent": 0}
	base.update(kw)
	return base


# ------------------------------------------------------------------ billing
def test_class_specific_structure_wins_and_services_billed():
	lines = compute_fee_lines(student(), STRUCTURES, FEE_TYPES, ROUTES, ACTS, ALL)
	got = {l["fee_type"]: l["amount"] for l in lines}
	assert got == {"Tuition": 25000, "Lunch": 6000, "Admission Fee": 5000, "Transport": 9000, "Games & Activities": 4000}
	assert [l["fee_type"] for l in lines][0] == "Tuition"  # priority order


def test_lunch_only_when_opted_in_and_boarding_only_for_boarders():
	lines = compute_fee_lines(student(takes_lunch=0, boarding_type="Boarder", transport_route=None, activities=[]),
							  STRUCTURES, FEE_TYPES, ROUTES, ACTS, ALL)
	got = {l["fee_type"] for l in lines}
	assert got == {"Tuition", "Boarding", "Admission Fee"}


def test_unlicensed_modules_are_not_billed():
	lines = compute_fee_lines(student(), STRUCTURES, FEE_TYPES, ROUTES, ACTS, ["core", "fees"])
	assert {l["fee_type"] for l in lines} == {"Tuition", "Admission Fee"}
	assert compute_fee_lines(student(), STRUCTURES, FEE_TYPES, ROUTES, ACTS, ["core"]) == []


def test_once_fees_not_repeated_and_scholarship_only_on_discountable():
	lines = compute_fee_lines(student(scholarship_percent=50), STRUCTURES, FEE_TYPES, ROUTES, ACTS, ALL, {"Admission Fee"})
	by = {l["fee_type"]: l for l in lines}
	assert "Admission Fee" not in by
	assert net_amount(by["Tuition"]) == 12500
	assert net_amount(by["Transport"]) == 9000


# ------------------------------------------------------------------ allocation
def test_split_invoice_paid_explicit_first_then_priority():
	lines = [{"fee_type": "Tuition", "amount": 25000, "priority": 1}, {"fee_type": "Transport", "amount": 9000, "priority": 4},
			 {"fee_type": "Lunch", "amount": 6000, "priority": 3}]
	# parent explicitly paid 9000 transport; another 10000 untagged
	paid = split_invoice_paid(lines, {"Transport": 9000}, 19000)
	assert paid == {"Tuition": 10000, "Lunch": 0, "Transport": 9000}
	# overpaid explicit never exceeds what is actually paid
	assert sum(split_invoice_paid(lines, {"Transport": 9000}, 5000).values()) == 5000


def open_lines():
	return [
		{"sales_invoice": "SI-2", "posting_date": "2026-05-01", "school_term": "Term 2 2026", "fee_type": "Tuition", "priority": 1, "outstanding": 25000},
		{"sales_invoice": "SI-2", "posting_date": "2026-05-01", "school_term": "Term 2 2026", "fee_type": "Transport", "priority": 4, "outstanding": 9000},
		{"sales_invoice": "SI-1", "posting_date": "2026-01-06", "school_term": "Term 1 2026", "fee_type": "Lunch", "priority": 3, "outstanding": 2000},
	]


def test_oldest_first():
	allocs, rest = allocate_payment(open_lines(), 10000)
	assert [(a["sales_invoice"], a["fee_type"], a["allocated_amount"]) for a in allocs] == [
		("SI-1", "Lunch", 2000), ("SI-2", "Tuition", 8000)]
	assert rest == 0


def test_targeted_transport_with_and_without_spill():
	allocs, rest = allocate_payment(open_lines(), 12000, ["Transport"], spill_over=True)
	assert [(a["fee_type"], a["allocated_amount"]) for a in allocs] == [("Transport", 9000), ("Lunch", 2000), ("Tuition", 1000)]
	allocs, rest = allocate_payment(open_lines(), 12000, ["Transport"], spill_over=False)
	assert [(a["fee_type"], a["allocated_amount"]) for a in allocs] == [("Transport", 9000)]
	assert rest == 3000


def test_overpayment_becomes_advance_and_invoice_totals():
	allocs, rest = allocate_payment(open_lines(), 40000)
	assert rest == 4000
	assert per_invoice_totals(allocs) == {"SI-1": 2000, "SI-2": 34000}


# ------------------------------------------------------------------ statement
def test_ledger_and_breakdown_reconcile():
	led = build_ledger(5000, [
		{"date": "2026-01-06", "details": "Term 1 fees", "kind": "charge", "debit": 40000, "credit": 0},
		{"date": "2026-01-10", "details": "Payment", "kind": "payment", "debit": 0, "credit": 30000},
		{"date": "2026-02-01", "details": "Fee credit", "kind": "adjustment", "debit": 0, "credit": 1000},
	])
	assert led["closing"] == 14000
	assert led["opening"] + led["charged"] + led["adjusted"] - led["paid"] == led["closing"]
	b = breakdown_rows([{"fee_type": "Tuition", "billed": 25000, "paid": 25000, "outstanding": 0, "priority": 1},
						{"fee_type": "Transport", "billed": 9000, "paid": 0, "outstanding": 9000, "priority": 4}], 5000, 0)
	assert b["total"]["outstanding"] == 14000


# ------------------------------------------------------------------ license
@lru_cache
def keys():
	return lic.generate_keypair()


def test_license_valid_grace_expired():
	priv, pub = keys()
	key = lic.issue({"school": "Greenhill", "modules": ["fees", "transport"], "expires": "2026-12-31", "max_students": 300}, priv)
	ok = lic.evaluate(key, pub, date(2026, 10, 21))
	assert ok["status"] == "valid" and ok["modules"] == ["core", "fees", "transport"] and ok["max_students"] == 300
	assert lic.check(ok, "lunch") and not lic.check(ok, "fees")
	grace = lic.evaluate(key, pub, date(2027, 1, 5))
	assert grace["status"] == "grace" and grace["writable"]
	exp = lic.evaluate(key, pub, date(2027, 3, 1))
	assert exp["status"] == "expired"
	assert lic.check(exp, "fees", "Fee Billing Run")
	assert lic.check(exp, "fees", "Fee Payment") is None  # money can always be receipted


def test_license_tampering_and_site_lock():
	priv, pub = keys()
	key = lic.issue({"school": "A", "modules": ["fees"], "site": "a.school.ke"}, priv)
	body, sig = key.split(".")
	import base64, json
	payload = json.loads(base64.urlsafe_b64decode(body + "=="))
	payload["modules"].append("messaging")
	forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=") + "." + sig
	assert lic.evaluate(forged, pub, date(2026, 1, 1))["status"] == "invalid"
	assert lic.evaluate(key, pub, date(2026, 1, 1), site="b.school.ke")["status"] == "invalid"
	assert lic.evaluate(key, pub, date(2026, 1, 1), site="a.school.ke")["status"] == "valid"
	assert lic.evaluate("", pub, date(2026, 1, 1))["modules"] == ["core"]


# ------------------------------------------------------------------ misc
def test_phone_and_templates():
	assert normalize_phone("0712 345 678") == "254712345678"
	assert normalize_phone("+254712345678") == "254712345678"
	assert normalize_phone("712345678") == "254712345678"
	assert normalize_phone("abc") is None
	assert render("Hi {guardian_name}, bal {balance} {unknown}", {"guardian_name": "Jane", "balance": "KES 5"}) == "Hi Jane, bal KES 5 {unknown}"


def test_timetable_clashes():
	slots = [{"day": "Monday", "period": "P1", "teacher": "T1"}, {"day": "Monday", "period": "P1", "teacher": "T2"}]
	assert find_duplicate_slots(slots)
	other = [{"day": "Monday", "period": "P1", "teacher": "T1", "timetable": "Grade 5 East - Term 1 2026", "teacher_name": "Mr Otieno"}]
	errs = find_teacher_clashes(slots[:1], other)
	assert errs and "Mr Otieno" in errs[0]


# ------------------------------------------------------------------ paybill
from school_erp.logic import paybill as pb  # noqa: E402


def test_account_number_normalisation():
	assert pb.account_key(" stu 2026-0042 ") == "STU20260042"
	assert pb.account_key("STU-2026-0042") == pb.account_key("stu20260042")
	assert pb.clean_ref("  stu-2026-0042 ") == "STU-2026-0042"


def test_payload_parsing():
	d = pb.normalize_payload({
		"TransactionType": "Pay Bill", "TransID": "sgl31hk2bo", "TransTime": "20261021153045", "TransAmount": "15000.00",
		"BusinessShortCode": "247247", "BillRefNumber": "stu-2026-0042", "OrgAccountBalance": "120500.00",
		"MSISDN": "2547 ***** 126", "FirstName": "GRACE", "MiddleName": "", "LastName": "KAMAU",
	})
	assert d["trans_id"] == "SGL31HK2BO"
	assert d["trans_time"].isoformat() == "2026-10-21T15:30:45"
	assert d["amount"] == 15000.0 and d["bill_ref_number"] == "STU-2026-0042"
	assert d["payer_name"] == "Grace Kamau"
	assert pb.parse_trans_time("garbage") is None


def test_ip_allowlist_and_urls():
	allowed = "196.201.212.0/24\n196.201.213.0/24, 196.201.214.0/24"
	assert pb.ip_allowed("196.201.214.200", allowed)
	assert not pb.ip_allowed("41.90.1.1", allowed)
	assert not pb.ip_allowed("not-an-ip", allowed)
	assert pb.url_problems("https://greenhill.example.com/api/method/school_erp.api.paybill.confirm") == []
	assert pb.url_problems("https://school-mpesa.example.com")  # forbidden word
	assert pb.url_problems("http://school.localhost:8000")
