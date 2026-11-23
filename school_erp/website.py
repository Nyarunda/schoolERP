"""The school's public website: branding for every web page, and the data the homepage shows.

Guests read only what is built here on the server: the School Settings website fields, the current year's terms and
the notices a school admin ticked for the website. Nothing new is opened to the API."""

import frappe
from frappe.utils import escape_html, formatdate, getdate, today

from school_erp.logic import website as rules

_FALLBACK_NAME = "Stemic Schools"


def _settings() -> frappe._dict:
	from school_erp.api.singles import get_settings

	return get_settings("School Settings")


def site_info(settings=None) -> frappe._dict:
	"""Who the school is and how it looks: used by the header, footer, sign-in page and navbar brand."""
	s = settings or _settings()
	name = (s.school_name or "").strip() or _FALLBACK_NAME
	color = rules.readable(s.site_color or s.statement_accent_color)
	return frappe._dict(
		name=name,
		motto=(s.motto or "").strip(),
		logo=s.school_logo or "",
		initials=rules.initials(name),
		color=color,
		color_dark=rules.readable(color, ratio=9),
		wash=rules.tint(color, 0.92),
		tagline=(s.site_tagline or "").strip(),
		phone=(s.phone or "").strip(),
		email=(s.email or "").strip(),
		address=(s.address or "").strip(),
		office_hours=(s.office_hours or "").strip(),
		map_link=_web_link(s.map_link),
		home_on=bool(s.website_home_on),
		year=getdate(today()).year,
	)


def _web_link(url: str | None) -> str:
	"""Only http(s) links reach a page: a typed "javascript:" never becomes a button."""
	url = (url or "").strip()
	return url if url.lower().startswith(("https://", "http://")) else ""


def brand_html(info) -> str:
	"""The crest (logo or initials) and name, for Frappe's standard navbar."""
	name = escape_html(info.name)
	if info.logo:
		crest = f'<img src="{escape_html(info.logo)}" alt="" style="height:36px;width:auto;margin-right:10px">'
	else:
		crest = (f'<span aria-hidden="true" style="display:inline-flex;align-items:center;justify-content:center;width:36px;'
				 f'height:36px;border-radius:10px;background:{info.color};color:#fff;font-weight:800;font-size:13px;'
				 f'margin-right:10px">{escape_html(info.initials)}</span>')
	return f'<span style="display:inline-flex;align-items:center;font-weight:700">{crest}{name}</span>'


def update_context(context):
	"""hooks.update_website_context: every web page gets the school's brand instead of "Home"."""
	try:
		info = site_info()
	except Exception:  # a half-installed site must still render its pages
		return None
	values = {"school_site": info, "brand_html": brand_html(info), "school_account": account_button()}
	if info.logo:
		values["favicon"] = info.logo
	return values


def account_button() -> dict:
	"""The header's right-hand button: Sign in for guests, My children for parents, the desk for staff."""
	user = frappe.session.user
	if user == "Guest":
		return {"label": "Sign in", "href": "/login"}
	if "Parent" in frappe.get_roles(user) and frappe.db.get_value("User", user, "user_type") == "Website User":
		return {"label": "My children", "href": "/parent"}
	return {"label": "Open the school system", "href": "/desk"}


def _licensed(module: str) -> bool:
	from school_erp import licensing

	try:
		return licensing.is_enabled(module)
	except Exception:
		return False


def home_context(settings=None) -> frappe._dict:
	"""Everything the homepage shows. Sections with nothing to show come back empty and are left out."""
	from school_erp.api.singles import get_settings

	s = settings or _settings()
	info = site_info(s)
	now = getdate(today())

	portal = _licensed("portal") and bool(s.portal_enabled)
	admissions = _licensed("admissions") and bool(get_settings("Admission Settings").accepting_applications)
	complaints = _licensed("welfare")

	cards = []
	if portal:
		cards.append(("parents", "Parent portal", "Fee balance, results, attendance and messages from the school.", "/parent"))
	if admissions:
		cards.append(("apply", "Apply for admission", "Apply online, then track your application with its reference number.",
					  "/admission-application"))
	cards.append(("fees", "How to pay fees", "M-Pesa and bank details. Payments show on your child's statement.", "#fees"))
	cards.append(("verify", "Verify a document", "Check that a report card, receipt or letter really came from the school.", "/verify"))
	cards.append(("staff", "Staff sign in", "Teachers, bursar and office staff.", "/login"))
	if complaints:
		cards.append(("contact", "Contact or raise a concern", "Call or write to the office, or send a complaint that gets a reference number.", "/complaint"))
	else:
		cards.append(("contact", "Contact the school", "Phone, email, office hours and directions.", "#contact"))

	terms = []
	if s.show_term_dates:
		rows = frappe.get_all("School Term", fields=["term_name", "school_year", "start_date", "end_date", "is_current"])
		for r in rows:
			r.start_date, r.end_date = getdate(r.start_date) if r.start_date else None, getdate(r.end_date) if r.end_date else None
		terms = rules.terms_for_year(rows, now)
		for t in terms:
			t["opens"] = formatdate(t["start_date"]) if t.get("start_date") else ""
			t["closes"] = formatdate(t["end_date"]) if t.get("end_date") else ""

	notices = []
	for n in frappe.get_all("School Notice", filters={"show_on_website": 1},
							fields=["title", "publish_date", "expiry_date", "pinned", "message", "creation"],
							order_by="pinned desc, publish_date desc, creation desc", limit=20):
		publish = getdate(n.publish_date) if n.publish_date else None
		if not rules.is_live(publish, getdate(n.expiry_date) if n.expiry_date else None, now):
			continue
		when = publish or getdate(n.creation)
		notices.append(frappe._dict(title=n.title, month=when.strftime("%b"), day=when.day,
									text=rules.excerpt(n.message, 160), full=rules.excerpt(n.message, 2000)))
		if len(notices) == 3:
			break

	return frappe._dict(
		site=info,
		intro=(s.site_intro or "").strip(),
		about=(s.site_about or "").strip(),
		photo=s.site_photo or "",
		photo_2=s.site_photo_2 or "",
		cards=cards,
		portal=portal,
		admissions=admissions,
		complaints=complaints,
		pay=rules.pay_steps(s.mpesa_account_type, s.paybill_number),
		bank=(s.bank_details or "").strip(),
		payment_note=rules.public_note(s.payment_instructions, s.mpesa_account_type, s.paybill_number, s.school_name),
		terms=terms,
		next_date=rules.next_date(terms, now),
		year=terms[0].school_year if terms else "",
		notices=notices,
		account=account_button(),
		this_year=now.year,
	)
