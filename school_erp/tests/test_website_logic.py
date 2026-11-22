"""Framework-free tests for the school website rules (no bench needed)."""

from datetime import date

from school_erp.logic.website import (DEFAULT_COLOR, contrast, excerpt, initials, is_live, next_date, pay_steps,
									   readable, terms_for_year, tint)


def test_initials():
	assert initials("Stemic Test School") == "STS"
	assert initials("St. Mary's Girls High School") == "SMG"
	assert initials("School of the Nations") == "SN"
	assert initials("") == "S" and initials(None) == "S"


def test_readable():
	assert contrast("#3cbd4d") < 4.5
	dark = readable("#3cbd4d")
	assert contrast(dark) >= 4.5 and dark != "#3cbd4d"
	assert readable("#166534") == "#166534"  # already fine: unchanged
	assert readable("#fff") != "#ffffff" and contrast(readable("#fff")) >= 4.5
	assert readable("not a colour") == DEFAULT_COLOR and readable(None) == DEFAULT_COLOR


def test_tint():
	assert tint("#000000", 0.5) == "#808080"
	assert tint("zzz") == tint(DEFAULT_COLOR)


def test_pay_steps_paybill():
	p = pay_steps("Paybill", " 123456 ")
	assert p["number"] == "123456" and p["kind"] == "Paybill"
	assert "admission number" in p["account"] and any("123456" in s for s in p["steps"])


def test_pay_steps_till_and_none():
	t = pay_steps("Till (Buy Goods)", "556677")
	assert t["kind"] == "Till" and t["account"] is None and "Buy Goods" in t["steps"][0]
	assert pay_steps("Paybill", "") is None and pay_steps("Paybill", None) is None


def test_excerpt():
	assert excerpt("<p>Hello&nbsp;<b>parents</b></p><p>Next</p>") == "Hello parents Next"
	long = "word " * 60
	cut = excerpt(long, 30)
	assert cut.endswith("…") and len(cut) <= 31
	assert excerpt(None) == ""


def test_is_live():
	today = date(2026, 11, 22)
	assert is_live(None, None, today)
	assert is_live(date(2026, 11, 22), date(2026, 11, 22), today)
	assert not is_live(date(2026, 11, 23), None, today)
	assert not is_live(None, date(2026, 11, 21), today)


def _t(name, year, start, end, current=0):
	return {"term_name": name, "school_year": year, "start_date": start, "end_date": end, "is_current": current}


def test_terms_for_year():
	today = date(2026, 6, 1)
	terms = [_t("Term 3", "2025", date(2025, 9, 1), date(2025, 11, 20)),
			 _t("Term 2", "2026", date(2026, 5, 4), date(2026, 8, 7)),
			 _t("Term 1", "2026", date(2026, 1, 5), date(2026, 4, 2))]
	assert [t["term_name"] for t in terms_for_year(terms, today)] == ["Term 1", "Term 2"]
	terms[0]["is_current"] = 1  # the marked current term wins
	assert [t["term_name"] for t in terms_for_year(terms, today)] == ["Term 3"]
	assert terms_for_year([], today) == []
	# nothing current, today in no term: the latest year
	assert terms_for_year(terms[1:], date(2027, 1, 1))[0]["school_year"] == "2026"


def test_next_date():
	terms = [_t("Term 1", "2026", date(2026, 1, 5), date(2026, 4, 2)),
			 _t("Term 2", "2026", date(2026, 5, 4), date(2026, 8, 7))]
	assert next_date(terms, date(2026, 4, 10)) == "Term 2 opens 4 May 2026"
	assert next_date(terms, date(2026, 2, 1)) == "Term 1 closes 2 April 2026"
	assert next_date(terms, date(2026, 9, 1)) is None
