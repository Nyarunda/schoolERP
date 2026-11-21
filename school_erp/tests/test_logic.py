"""Framework-free tests: run with  pytest school_erp/tests/test_logic.py  (no bench needed)."""

from datetime import date
from functools import lru_cache

from school_erp.logic import license as lic
from school_erp.logic.allocation import allocate_payment, per_invoice_totals, split_invoice_paid
from school_erp.logic.billing import compute_fee_lines, net_amount
from school_erp.logic.statement import breakdown_rows, build_ledger
from school_erp.logic.text import normalize_phone, render
from school_erp.logic.timetable import find_duplicate_slots, find_teacher_clashes, session_blocks, session_labels

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


def test_double_lessons_merge_only_when_back_to_back():
	periods = [
		{"name": "P1", "sequence": 1, "start_time": "8:00:00", "end_time": "8:40:00"},
		{"name": "P2", "sequence": 2, "start_time": "8:40:00", "end_time": "9:20:00"},
		{"name": "Break", "sequence": 3, "start_time": "9:20:00", "end_time": "9:30:00"},
		{"name": "P3", "sequence": 4, "start_time": "9:30:00", "end_time": "10:10:00"},
	]
	slots = [
		{"day": "Monday", "period": "P2", "subject": "Maths", "teacher": "T1"},
		{"day": "Monday", "period": "P1", "subject": "Maths", "teacher": "T1"},
		{"day": "Monday", "period": "P3", "subject": "Maths", "teacher": "T1"},  # after the break: its own session
		{"day": "Tuesday", "period": "P1", "subject": "English", "teacher": "T2"},
		{"day": "Tuesday", "period": "P2", "subject": "English", "teacher": "T3"},  # other teacher: not a double
	]
	blocks = session_blocks(slots, periods)
	assert [(b["day"], b["size"], b["start"], b["end"]) for b in blocks] == [
		("Monday", 2, "08:00", "09:20"), ("Monday", 1, "09:30", "10:10"),
		("Tuesday", 1, "08:00", "08:40"), ("Tuesday", 1, "08:40", "09:20")]
	labels = session_labels(slots, periods)
	assert labels[id(slots[0])] == ("08:00-09:20", "Double 2/2")
	assert labels[id(slots[1])] == ("08:00-09:20", "Double 1/2")
	assert labels[id(slots[2])] == ("09:30-10:10", "")


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


# ------------------------------------------------------------------ staff, approvals, vehicles
from school_erp.logic import operations as ops  # noqa: E402


def test_leave_days_skip_weekends_and_holidays():
	# Fri 23 Oct 2026 -> Tue 27 Oct 2026; Mon 26 is a holiday
	assert ops.leave_days(date(2026, 10, 23), date(2026, 10, 27)) == 3
	assert ops.leave_days(date(2026, 10, 23), date(2026, 10, 27), holidays={date(2026, 10, 26)}) == 2
	assert ops.leave_days(date(2026, 10, 23), date(2026, 10, 27), include_weekends=True) == 5
	assert ops.leave_days(date(2026, 10, 27), date(2026, 10, 23)) == 0


def leave_app(**kw):
	base = {"from_date": date(2026, 11, 2), "to_date": date(2026, 11, 4), "total_days": 3, "reliever": "STF-0002", "attachment": None}
	base.update(kw)
	return base


ANNUAL = {"days_per_year": 21, "requires_reliever": 1, "gender": "All", "applies_to": "All"}
STAFF = {"name": "STF-0001", "gender": "Female", "staff_type": "Teaching"}


def test_leave_rules():
	assert ops.leave_problems(leave_app(), ANNUAL, STAFF, taken_days=0, overlapping=[]) == []
	assert any("remain" in p for p in ops.leave_problems(leave_app(), ANNUAL, STAFF, 20, []))
	assert any("reliever is required" in p for p in ops.leave_problems(leave_app(reliever=None), ANNUAL, STAFF, 0, []))
	assert any("own reliever" in p for p in ops.leave_problems(leave_app(reliever="STF-0001"), ANNUAL, STAFF, 0, []))
	assert any("on leave" in p for p in ops.leave_problems(leave_app(), ANNUAL, STAFF, 0, [], reliever_busy=True))
	assert any("overlap" in p for p in ops.leave_problems(leave_app(), ANNUAL, STAFF, 0, ["LV-2026-00001"]))
	paternity = {"days_per_year": 14, "gender": "Male"}
	assert any("male staff" in p for p in ops.leave_problems(leave_app(reliever=None), paternity, STAFF, 0, []))
	sick = {"days_per_year": 14, "requires_attachment": 1}
	assert any("Attach" in p for p in ops.leave_problems(leave_app(reliever=None), sick, STAFF, 0, []))
	unpaid = {"days_per_year": 0}
	assert ops.leave_problems(leave_app(reliever=None, total_days=40), unpaid, STAFF, 100, []) == []


def test_expense_approval_levels():
	assert ops.levels_required(8000, 10000) == 1
	assert ops.levels_required(25000, 10000) == 2
	assert ops.levels_required(100, 0) == 2
	a1 = [{"level": "First", "user": "bursar@x", "action": "Approved"}]
	assert ops.next_level(1, []) == "First" and ops.next_level(1, a1) is None
	assert ops.next_level(2, a1) == "Final"
	assert ops.status_for(2, a1) == "Pending Final Approval"
	assert ops.status_for(1, a1) == "Approved"
	assert ops.status_for(2, a1 + [{"level": "Final", "user": "head@x", "action": "Rejected"}]) == "Rejected"
	# separation of duties
	assert ops.approval_error("clerk@x", "clerk@x", "First", {"Bursar"}, "Bursar", [])
	assert ops.approval_error("bursar@x", "clerk@x", "Final", {"Bursar", "Head Teacher"}, "Head Teacher", a1)
	assert ops.approval_error("teacher@x", "clerk@x", "First", {"Teacher"}, "Bursar", [])
	assert ops.approval_error("head@x", "clerk@x", "Final", {"Head Teacher"}, "Head Teacher", a1) is None


def test_vehicle_checks():
	ok = [{"item": i, "ok": 1} for i in ops.DEFAULT_CHECKLIST]
	assert ops.vehicle_problems(ok, True, date(2026, 10, 21)) == []
	bad = ok[:1] + [{"item": "Brakes", "ok": 0, "remarks": "soft pedal"}]
	probs = ops.vehicle_problems(bad, False, date(2026, 10, 21), insurance_expiry=date(2026, 10, 1))
	assert "Brakes: NOT OK - soft pedal" in probs
	assert any("fitness" in p for p in probs) and any("Insurance expired" in p for p in probs)


def test_billing_run_summary_counts_only_ticked_students():
	from school_erp.logic.billing import describe_lines, summarize_run

	a = [{"fee_type": "Tuition", "amount": 25000, "priority": 1}, {"fee_type": "Lunch", "amount": 6000, "priority": 3}]
	b = [{"fee_type": "Tuition", "amount": 25000, "discount_percent": 50, "priority": 1}]
	c = [{"fee_type": "Tuition", "amount": 25000, "priority": 1}, {"fee_type": "Transport", "amount": 9000, "priority": 4}]
	s = summarize_run([{"include": 1, "lines": a}, {"include": 1, "lines": b}, {"include": 0, "lines": c}])
	assert s["students"] == 2
	assert s["amount"] == 25000 + 6000 + 12500
	assert [(r["fee_type"], r["students"], r["amount"]) for r in s["by_fee_type"]] == [("Tuition", 2, 37500), ("Lunch", 1, 6000)]
	assert describe_lines(b) == "Tuition 12,500 (-50%)"


# ------------------------------------------------------------------ exams & promotion
from school_erp.logic import exams as ex  # noqa: E402
from school_erp.logic import promotion as pr  # noqa: E402


def test_grading_edges():
	assert ex.grade_for(80, ex.KCSE_BANDS)["grade"] == "A"
	assert ex.grade_for(79.995, ex.KCSE_BANDS)["grade"] == "A"  # rounds to 80
	assert ex.grade_for(79.99, ex.KCSE_BANDS)["grade"] == "A-"
	assert ex.grade_for(0, ex.KCSE_BANDS)["grade"] == "E"
	assert ex.grade_for(55, ex.CBC_BANDS) == {"grade": "ME", "points": 3.0, "remark": "Meeting Expectations"}
	assert ex.grade_for(None, ex.CBC_BANDS)["grade"] == ""


def test_competition_rank_ties():
	assert ex.competition_rank({"a": 90, "b": 80, "c": 80, "d": 70, "e": None}) == {"a": 1, "b": 2, "c": 2, "d": 4}


def test_build_results_absent_and_means():
	marks = {
		"S1": {"Math": {"marks": 80}, "Eng": {"marks": 60}},
		"S2": {"Math": {"marks": 40}, "Eng": {"absent": True}},
		"S3": {"Math": {"absent": True}, "Eng": {"absent": True}},
	}
	r = ex.build_results(marks, {"Math": 100, "Eng": 100}, ex.KCSE_BANDS)
	assert r["S1"]["mean_percent"] == 70 and r["S1"]["mean_grade"] == "B+"
	assert r["S1"]["mean_points"] == (12 + 8) / 2
	assert r["S2"]["mean_percent"] == 40 and r["S2"]["subjects"]["Eng"]["grade"] == "ABS"  # absent excluded
	assert r["S3"]["mean_percent"] is None and r["S3"]["sat"] == 0
	pos = ex.subject_positions(r)
	assert pos["Math"] == {"S1": 1, "S2": 2}
	assert "Improved by 5%" in ex.auto_remark(70, 65) and "Dropped" in ex.auto_remark(60, 70)


def test_promotion_plan():
	assert pr.plan_student("Grade 4", "Grade 4 East", "Grade 5") == {"action": "Promote", "new_class": "Grade 5", "new_stream": "Grade 5 East"}
	assert pr.plan_student("Grade 9", "Grade 9 West", None)["action"] == "Graduate"
	assert pr.apply_action("Repeat", "Grade 4", "Grade 4 East", "Grade 5") == {"action": "Repeat", "new_class": "Grade 4", "new_stream": "Grade 4 East"}
	assert pr.apply_action("Promote", "Grade 9", "Grade 9 West", None)["action"] == "Graduate"
	s = pr.summarize([{"action": "Promote", "balance": 5000}, {"action": "Graduate", "balance": 0}, {"action": "Repeat", "balance": 100}])
	assert (s["promote"], s["graduate"], s["repeat"], s["with_balance"], s["balance"]) == (1, 1, 1, 2, 5100)


def test_paybill_and_till_wording_and_stk_parties():
	assert pb.is_till("Till (Buy Goods)") and not pb.is_till("Paybill") and not pb.is_till(None)
	assert pb.pay_line("Paybill", "522522", "STU-1") == "M-Pesa Paybill 522522, Account STU-1"
	assert pb.pay_line("Till (Buy Goods)", "8812345", "STU-1") == "M-Pesa Buy Goods, Till 8812345"
	assert pb.pay_line("Paybill", "", "STU-1") == ""
	assert pb.stk_parties("Paybill", "522522", "522522") == ("CustomerPayBillOnline", "522522")
	# a Till is authenticated with its store number but the money goes to the till
	assert pb.stk_parties("Till (Buy Goods)", "7712345", "8812345") == ("CustomerBuyGoodsOnline", "8812345")


def test_vat_inside_an_inclusive_amount():
	from decimal import Decimal

	from school_erp.logic.tax import vat_in

	assert vat_in(1160, 16) == Decimal("160.00")
	assert vat_in(100, 16) == Decimal("13.79")
	assert vat_in(5000, 0) == Decimal("0.00")


def test_supplier_payment_splits_add_up():
	from decimal import Decimal

	from school_erp.logic.tax import expense_split

	# not VAT-registered, plain supplier: the whole amount is cost, paid in full
	plain = expense_split(10000)
	assert (plain["expense"], plain["input_vat"], plain["paid"]) == (Decimal("10000.00"), 0, Decimal("10000.00"))

	# registered school, supplier charged VAT, 5% withholding on a professional fee, 2% VAT withholding agent
	s = expense_split(11600, supplier_charged_vat=True, school_vat_registered=True, wht_rate=5, vat_wht_rate=2)
	assert s["vat"] == s["input_vat"] == Decimal("1600.00")
	assert s["taxable_value"] == s["expense"] == Decimal("10000.00")
	assert (s["wht"], s["vat_wht"], s["paid"]) == (Decimal("500.00"), Decimal("200.00"), Decimal("10900.00"))

	# not registered: VAT is part of the cost, nothing to claim
	u = expense_split(11600, supplier_charged_vat=True, school_vat_registered=False, wht_rate=5)
	assert (u["expense"], u["input_vat"], u["wht"]) == (Decimal("11600.00"), 0, Decimal("500.00"))

	# no VAT charged: no VAT withholding even for an agent
	assert expense_split(5000, vat_wht_rate=2)["vat_wht"] == 0

	for case in (s, u, expense_split(333.33, supplier_charged_vat=True, school_vat_registered=True, wht_rate=3, vat_wht_rate=2)):
		assert case["expense"] + case["input_vat"] == case["paid"] + case["wht"] + case["vat_wht"]


def test_kra_pin_format():
	from school_erp.logic.tax import valid_pin

	assert valid_pin("P051234567X") and valid_pin("a123456789z")
	assert not valid_pin("P05123456X") and not valid_pin("") and not valid_pin("X051234567P")


# ----------------------------------------------------------------------------- class attendance
def test_attendance_summary_counts_late_as_attending():
	from school_erp.logic.attendance import summarise

	s = summarise(["Present", "Present", "Late", "Absent", "Excused"])
	assert (s["present"], s["late"], s["absent"], s["excused"], s["total_students"]) == (2, 1, 1, 1, 5)
	assert s["attendance_percent"] == 60.0
	assert summarise([])["attendance_percent"] == 0.0


def test_attendance_rate_and_newly_absent():
	from school_erp.logic.attendance import newly_absent, rate

	assert rate(19, 20) == 95.0 and rate(0, 0) is None
	old = {"A": "Absent", "B": "Present"}
	new = {"A": "Absent", "B": "Absent", "C": "Absent", "D": "Late"}
	assert sorted(newly_absent(old, new)) == ["B", "C"]  # A was already absent: the parent was told once


def test_move_kind():
	from school_erp.logic.promotion import move_kind

	assert move_kind(5, 4) == "back"
	assert move_kind(4, 5) == "up"
	assert move_kind(4, 4) == "same class"
	assert move_kind(None, 4) == "same class"
