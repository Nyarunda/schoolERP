"""Framework-free tests for CBC rubric maths (no bench needed)."""

from school_erp.logic.cbc import (
	EIGHT_LEVEL,
	FOUR_LEVEL,
	band,
	distribution,
	distribution_text,
	level_for,
	levels,
	points_for,
	roll_up,
	strengths_and_gaps,
)


def test_levels_and_points():
	assert levels(FOUR_LEVEL) == ["EE", "ME", "AE", "BE"]
	assert levels(None) == ["EE", "ME", "AE", "BE"]
	assert levels(EIGHT_LEVEL)[0] == "EE1" and len(levels(EIGHT_LEVEL)) == 8
	assert points_for("ME", FOUR_LEVEL) == 3
	assert points_for("EE2", EIGHT_LEVEL) == 7
	assert points_for("EE1", FOUR_LEVEL) is None  # a level from the other rubric is not counted
	assert points_for("", FOUR_LEVEL) is None


def test_level_for_rounds_halves_up_and_clamps():
	assert level_for(3.5, FOUR_LEVEL)["level"] == "EE"
	assert level_for(3.49, FOUR_LEVEL)["level"] == "ME"
	assert level_for(1.0, FOUR_LEVEL) == {"level": "BE", "points": 1.0, "descriptor": "Below Expectations"}
	assert level_for(9, FOUR_LEVEL)["level"] == "EE"
	assert level_for(0, FOUR_LEVEL)["level"] == "BE"
	assert level_for(None, FOUR_LEVEL)["level"] == ""
	assert level_for(6.5, EIGHT_LEVEL)["level"] == "EE2"


def test_band_and_distribution():
	assert band("EE1") == "EE" and band("me") == "" and band(None) == ""
	assert distribution(["EE", "EE1", "ME2", "BE", "", None]) == {"EE": 2, "ME": 1, "AE": 0, "BE": 1}
	assert distribution_text(["EE", "ME", "ME"]) == "EE 1 · ME 2"


def test_roll_up_weights_each_strand_once():
	results = [
		# Maths: strand Numbers assessed 3 times at EE, strand Geometry once at AE -> (4 + 2) / 2 = 3 -> ME
		{"student": "S1", "subject": "Maths", "strand": "Numbers", "level": "EE"},
		{"student": "S1", "subject": "Maths", "strand": "Numbers", "level": "EE"},
		{"student": "S1", "subject": "Maths", "strand": "Numbers", "level": "EE"},
		{"student": "S1", "subject": "Maths", "strand": "Geometry", "level": "AE"},
		{"student": "S1", "subject": "English", "strand": "Reading", "level": "BE"},
		{"student": "S1", "subject": "English", "strand": "Reading", "level": ""},  # not assessed: ignored
		{"student": "S2", "subject": "Maths", "strand": "Numbers", "level": "ME"},
	]
	out = roll_up(results, FOUR_LEVEL)
	assert out["S1"]["Maths"] == {"level": "ME", "points": 3.0, "descriptor": "Meeting Expectations", "strands": 2, "assessments": 4}
	assert out["S1"]["English"]["level"] == "BE"
	assert out["S1"]["English"]["assessments"] == 1
	assert out["S2"]["Maths"]["level"] == "ME"


def test_strengths_and_gaps():
	areas = {"MAT": {"points": 4.0}, "ENG": {"points": 2.0}, "KIS": {"points": 4.0}, "SCI": {"points": None}}
	strong, weak = strengths_and_gaps(areas, {"MAT": "Mathematics", "KIS": "Kiswahili", "ENG": "English"})
	assert strong == "Kiswahili, Mathematics"
	assert weak == "English"
	assert strengths_and_gaps({"MAT": {"points": 3.0}}) == ("MAT", "")
	assert strengths_and_gaps({}) == ("", "")
