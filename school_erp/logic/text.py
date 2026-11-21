"""Message templating and phone normalisation."""

import re

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def render(template: str, context: dict) -> str:
	"""Fill {placeholders}; unknown ones are left as-is instead of raising."""
	if not template:
		return ""

	def sub(m):
		key = m.group(1)
		if key not in context:
			return m.group(0)
		value = context[key]
		return "" if value is None else str(value)

	return _PLACEHOLDER.sub(sub, template)


def normalize_phone(raw: str | None, country_code: str = "254") -> str | None:
	"""07XX XXX XXX / +2547XXXXXXXX / 7XXXXXXXX -> 2547XXXXXXXX (digits only). Returns None if unusable."""
	if not raw:
		return None
	digits = re.sub(r"\D", "", str(raw))
	cc = re.sub(r"\D", "", country_code or "")
	if not digits:
		return None
	if digits.startswith("00"):
		digits = digits[2:]
	elif cc and digits.startswith(cc):
		pass
	elif digits.startswith("0"):
		digits = cc + digits[1:]
	elif cc and len(digits) <= 10:
		digits = cc + digits
	return digits if 9 <= len(digits) <= 15 else None


def phone_variants(raw: str | None, country_code: str = "254") -> list[str]:
	"""Every form a phone may be stored in (0712345678, 254712345678, +254712345678), for matching logins."""
	full = normalize_phone(raw, country_code)
	if not full:
		return []
	cc = re.sub(r"\D", "", country_code or "")
	out = [full, "+" + full]
	if cc and full.startswith(cc):
		out.append("0" + full[len(cc):])
	return out


def sms_parts(message: str) -> int:
	n = len(message or "")
	return 1 if n <= 160 else -(-n // 153)
