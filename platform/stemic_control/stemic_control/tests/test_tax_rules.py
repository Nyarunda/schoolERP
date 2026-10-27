"""Pure tax-rule checks. No pytest import: Frappe's test runner imports every tests/test_*.py, and bench
environments (CI included) do not ship pytest."""
from contextlib import contextmanager

from stemic_control.tax_rules import valid_pin, validate_amounts


@contextmanager
def raises(error):
    try:
        yield
    except error:
        return
    raise AssertionError(f"{error.__name__} was not raised")


def test_pin_format():
    assert valid_pin("P051234567X")
    assert not valid_pin("NO-PIN")
    assert not valid_pin("P123")


def test_exempt_zero_tax():
    assert validate_amounts("1000", "0", "1000", "Exempt")[2] == 1000
    with raises(ValueError):
        validate_amounts("1000", "160", "1160", "Exempt")


def test_balancing_and_manual_classification():
    with raises(ValueError):
        validate_amounts("1000", "160", "1200", "Standard Rated")
    with raises(ValueError):
        validate_amounts("1000", "0", "1000", "Review Required")


def test_reject_zero_amount_and_invalid_precision():
    with raises(ValueError):
        validate_amounts("0", "0", "0", "Exempt")
    with raises(ValueError):
        validate_amounts("12.345", "0", "12.345", "Exempt")
    with raises(ValueError):
        validate_amounts("NaN", "0", "100", "Exempt")
