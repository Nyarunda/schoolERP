"""Kenya tax arithmetic (no Frappe): VAT inside an inclusive amount, and how a supplier payment splits.

Rates are not hard-coded rules: the school sets them (School Settings > Tax, Withholding Tax Type) after checking
with KRA or its tax adviser. Money is handled in Decimal and rounded to cents, and every split adds back up exactly.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

PIN = re.compile(r"^[AP][0-9]{9}[A-Z]$")  # A = individual, P = organisation

EXEMPT, ZERO_RATED, STANDARD = "Exempt", "Zero Rated", "Standard Rated"
TREATMENTS = (EXEMPT, ZERO_RATED, STANDARD)
CENT = Decimal("0.01")


def valid_pin(pin) -> bool:
	return bool(PIN.fullmatch(str(pin or "").strip().upper()))


def _d(value) -> Decimal:
	return Decimal(str(value or 0))


def _cents(value: Decimal) -> Decimal:
	return value.quantize(CENT, rounding=ROUND_HALF_UP)


def vat_in(amount, rate) -> Decimal:
	"""The VAT inside a VAT-inclusive amount: amount x rate / (100 + rate)."""
	rate = _d(rate)
	if rate <= 0:
		return Decimal("0.00")
	return _cents(_d(amount) * rate / (100 + rate))


def expense_split(amount, *, supplier_charged_vat=False, vat_rate=16, school_vat_registered=False,
				  wht_rate=0, vat_wht_rate=0) -> dict:
	"""How a supplier invoice of `amount` (what the supplier billed, VAT included if they charged it) is posted.

	- VAT the supplier charged is claimable input VAT only for a VAT-registered school; otherwise it is part of
	  the cost.
	- Withholding tax (income tax) is withheld on the amount before VAT.
	- VAT withholding (for appointed agents) is withheld on the same base, and only when VAT was charged.
	The supplier is paid the rest.
	"""
	amount = _cents(_d(amount))
	vat = vat_in(amount, vat_rate) if supplier_charged_vat else Decimal("0.00")
	base = amount - vat
	input_vat = vat if school_vat_registered else Decimal("0.00")
	wht = _cents(base * _d(wht_rate) / 100)
	vat_wht = _cents(base * _d(vat_wht_rate) / 100) if vat else Decimal("0.00")
	return {
		"vat": vat,
		"taxable_value": base,
		"expense": amount - input_vat,
		"input_vat": input_vat,
		"wht": wht,
		"vat_wht": vat_wht,
		"paid": amount - wht - vat_wht,
	}
