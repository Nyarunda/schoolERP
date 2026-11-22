"""Rules for the school's public website (homepage, sign-in, paused page). Framework-free, unit tested."""

import html
import re
from datetime import date

from school_erp.logic.paybill import is_till

DEFAULT_COLOR = "#166534"  # a deep green that reads well with white text
_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_SMALL = {"of", "and", "the", "for", "&", "de"}


def initials(name: str | None, most: int = 3) -> str:
	"""Letters for a crest when the school has no logo: 'Stemic Test School' -> 'STS', 'St. Mary's Girls' -> 'SMG'."""
	words = [w for w in re.split(r"[\s\-]+", (name or "").strip()) if w and w.lower() not in _SMALL]
	letters = "".join(w[0] for w in words if w[0].isalnum()).upper()
	return letters[:most] or "S"


def _rgb(color: str) -> tuple[int, int, int] | None:
	m = _HEX.match((color or "").strip())
	if not m:
		return None
	h = m.group(1)
	if len(h) == 3:
		h = "".join(c * 2 for c in h)
	return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _luminance(rgb) -> float:
	def chan(c):
		c = c / 255
		return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

	r, g, b = (chan(c) for c in rgb)
	return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str = "#ffffff") -> float:
	"""WCAG contrast ratio between two colours (1 to 21)."""
	la, lb = _luminance(_rgb(a)), _luminance(_rgb(b))
	hi, lo = max(la, lb), min(la, lb)
	return (hi + 0.05) / (lo + 0.05)


def readable(color: str | None, against: str = "#ffffff", ratio: float = 4.5) -> str:
	"""The school's colour, darkened just enough for white text on it to pass `ratio`. Bad input -> the default."""
	rgb = _rgb(color or "")
	if not rgb:
		return DEFAULT_COLOR
	for _ in range(40):
		hexed = "#{:02x}{:02x}{:02x}".format(*rgb)
		if contrast(hexed, against) >= ratio:
			return hexed
		rgb = tuple(int(c * 0.92) for c in rgb)
	return "#{:02x}{:02x}{:02x}".format(*rgb)


def tint(color: str, amount: float = 0.9) -> str:
	"""A pale wash of `color` for backgrounds: mixed `amount` of the way to white."""
	rgb = _rgb(color) or _rgb(DEFAULT_COLOR)
	return "#{:02x}{:02x}{:02x}".format(*(round(c + (255 - c) * amount) for c in rgb))


def pay_steps(account_type: str | None, number: str | None) -> dict | None:
	"""What the fees panel shows: the number, the account to type, and the steps. None when no number is set."""
	number = (number or "").strip()
	if not number:
		return None
	if is_till(account_type):
		return {"kind": "Till", "label": "M-Pesa Till (Buy Goods)", "number": number, "account": None,
				"steps": ["Go to M-Pesa, then Lipa na M-Pesa, then Buy Goods and Services",
						  f"Till number: {number}", "Enter the amount and your M-Pesa PIN",
						  "Keep the M-Pesa message: the school matches it to your phone number"]}
	return {"kind": "Paybill", "label": "M-Pesa Paybill", "number": number, "account": "your child's admission number",
			"steps": ["Go to M-Pesa, then Lipa na M-Pesa, then Pay Bill", f"Business number: {number}",
					  "Account number: your child's admission number", "Enter the amount and your M-Pesa PIN"]}


def excerpt(text: str | None, most: int = 160) -> str:
	"""Plain text from a notice's HTML, cut at a word boundary."""
	plain = re.sub(r"<(br|/p|/div|/li)[^>]*>", " ", text or "", flags=re.I)
	plain = html.unescape(re.sub(r"<[^>]+>", "", plain))
	plain = re.sub(r"\s+", " ", plain).strip()
	if len(plain) <= most:
		return plain
	cut = plain[:most].rsplit(" ", 1)[0].rstrip(",.;:")
	return cut + "…"


def is_live(publish_date, expiry_date, today: date) -> bool:
	"""A notice shows from its publish date (or at once) until the end of its expiry date (or forever)."""
	return (not publish_date or publish_date <= today) and (not expiry_date or expiry_date >= today)


def terms_for_year(terms: list[dict], today: date) -> list[dict]:
	"""The terms of the school year to show: the current term's year, else the year that contains today, else the
	latest year. Each term dict has school_year, start_date, end_date, is_current."""
	if not terms:
		return []
	year = next((t["school_year"] for t in terms if t.get("is_current")), None)
	if not year:
		year = next((t["school_year"] for t in terms
					 if t.get("start_date") and t.get("end_date") and t["start_date"] <= today <= t["end_date"]), None)
	if not year:
		year = max(terms, key=lambda t: t.get("start_date") or date.min)["school_year"]
	return sorted((t for t in terms if t["school_year"] == year), key=lambda t: t.get("start_date") or date.min)


def next_date(terms: list[dict], today: date) -> str | None:
	"""A short line for the hero: the next term opening or closing, e.g. 'Term 2 opens 4 May 2026'."""
	events = []
	for t in terms:
		if t.get("start_date") and t["start_date"] >= today:
			events.append((t["start_date"], f"{t['term_name']} opens"))
		if t.get("end_date") and t["end_date"] >= today:
			events.append((t["end_date"], f"{t['term_name']} closes"))
	if not events:
		return None
	when, what = min(events)
	return f"{what} {when.day} {when.strftime('%B %Y')}"
