import pytest
from stemic_control.tax_rules import valid_pin, validate_amounts


def test_pin_format():
    assert valid_pin("P051234567X")
    assert not valid_pin("NO-PIN")
    assert not valid_pin("P123")


def test_exempt_zero_tax():
    assert validate_amounts("1000", "0", "1000", "Exempt")[2] == 1000
    with pytest.raises(ValueError):
        validate_amounts("1000", "160", "1160", "Exempt")


def test_balancing_and_manual_classification():
    with pytest.raises(ValueError):
        validate_amounts("1000", "160", "1200", "Standard Rated")
    with pytest.raises(ValueError):
        validate_amounts("1000", "0", "1000", "Review Required")
