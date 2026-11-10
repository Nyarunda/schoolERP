"""Framework-free tests for learner IDs and census maths (no bench needed)."""

from datetime import date

from school_erp.logic.nemis import age_gender_matrix, age_on, class_summary, clean_id, id_problem, missing_items


def test_clean_id_strips_spaces_and_uppercases():
	assert clean_id("  ab 12 c3 ") == "AB12C3"
	assert clean_id(None) == ""


def test_id_problem():
	assert id_problem("", "UPI") is None
	assert id_problem("AB12C3", "UPI") is None
	assert id_problem("12345/2019", "Birth certificate") is None
	assert "UPI" in id_problem("A$", "UPI")
	assert id_problem("x" * 21, "UPI")


def test_age_on_birthday_boundaries():
	assert age_on(date(2015, 5, 10), date(2026, 5, 9)) == 10
	assert age_on(date(2015, 5, 10), date(2026, 5, 10)) == 11
	assert age_on("2015-05-10", date(2026, 12, 31)) == 11
	assert age_on(None, date(2026, 1, 1)) is None
	assert age_on(date(2030, 1, 1), date(2026, 1, 1)) is None


def test_missing_items():
	full = {"upi_number": "A1", "birth_certificate_no": "B1", "date_of_birth": "2015-01-01", "gender": "Male"}
	assert missing_items(full) == []
	assert missing_items({**full, "upi_number": ""}) == ["UPI"]
	assert missing_items({}) == ["UPI", "Birth Cert", "Date of Birth", "Gender"]


def test_class_summary_counts_and_completeness():
	rows = [
		{"school_class": "Grade 4", "gender": "Male", "upi_number": "A", "birth_certificate_no": "1", "date_of_birth": "2016-01-01"},
		{"school_class": "Grade 4", "gender": "Female", "upi_number": "", "birth_certificate_no": "2", "date_of_birth": "2016-01-01",
		 "special_needs": 1},
		{"school_class": "Grade 5", "gender": "Female", "upi_number": "C", "birth_certificate_no": "", "date_of_birth": None},
	]
	g4, g5 = class_summary(rows)
	assert (g4["school_class"], g4["boys"], g4["girls"], g4["total"]) == ("Grade 4", 1, 1, 2)
	assert (g4["missing_upi"], g4["special_needs"], g4["complete"], g4["percent_complete"]) == (1, 1, 1, 50.0)
	assert (g5["missing_birth_cert"], g5["complete"]) == (1, 0)


def test_age_gender_matrix():
	on = date(2026, 1, 15)
	rows = [{"date_of_birth": "2016-01-01", "gender": "Male"}, {"date_of_birth": "2016-06-01", "gender": "Female"},
			{"date_of_birth": "2015-06-01", "gender": "Female"}, {"date_of_birth": None, "gender": "Male"}]
	m = age_gender_matrix(rows, on)
	assert list(m) == [9, 10, None]
	assert m[10] == {"Male": 1, "Female": 1}
	assert m[None] == {"Male": 1, "Female": 0}
