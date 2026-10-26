"""Tax validation primitives. Classification must be approved by the seller's tax adviser."""
import re
from decimal import Decimal, InvalidOperation

PIN = re.compile(r"^[AP][0-9]{9}[A-Z]$")
TREATMENTS = {"Exempt", "Zero Rated", "Standard Rated"}


def valid_pin(pin):
    return bool(PIN.fullmatch(str(pin or "").strip().upper()))


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError("Amount must be non-negative to two decimal places")
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid monetary amount") from exc


def validate_amounts(net, tax, total, treatment):
    if treatment not in TREATMENTS:
        raise ValueError("Choose an approved tax classification")
    net, tax, total = money(net), money(tax), money(total)
    if net + tax != total:
        raise ValueError("Invoice total must equal net plus tax")
    if treatment in {"Exempt", "Zero Rated"} and tax != 0:
        raise ValueError("Exempt and zero-rated invoices cannot contain output VAT")
    # Tax rate for Standard Rated must come from approved mapping, not hard-coded here.
    return net, tax, total
