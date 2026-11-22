"""A suspended school's site answers every request with "service suspended": pages, the desk, the API, logins.

The Control Center suspends a school by setting `stemic_suspended` (and pausing the scheduler) in the site's
site_config.json, and clears it on resume. This check runs before every request (hooks.before_request), so users
who are already signed in are stopped on their next click too. Stylesheets and images still load, so the page
renders properly.
"""

import json
import os

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

PASS_THROUGH = ("/assets/", "/files/", "/favicon.ico", "/robots.txt")
DEFAULT_MESSAGE = "This school's Stemic Schools service is suspended. Contact Stemic Schools to restore it."


_seen = {}  # site_config.json path -> (modified time, its contents): re-read only when the file changes


def _config_path():
	return os.path.join(frappe.local.site_path, "site_config.json")


def _site_config():
	"""This site's site_config.json as it is on disk now. Frappe's own copy for web requests (frappe.conf) is cached
	for up to a minute per worker, too long for a suspension (or a resumption) to wait."""
	path = _config_path()
	try:
		mtime = os.stat(path).st_mtime_ns
	except OSError:
		return frappe.conf
	hit = _seen.get(path)
	if not hit or hit[0] != mtime:
		try:
			with open(path) as f:
				hit = (mtime, frappe._dict(json.load(f)))
		except (OSError, ValueError):  # half-written by set-config: use what Frappe has
			return frappe.conf
		_seen[path] = hit
	return hit[1]


def suspended() -> bool:
	return bool(_site_config().get("stemic_suspended"))


def check():
	"""before_request: refuse everything while the site is suspended."""
	if not suspended() or not getattr(frappe.local, "request", None):
		return
	path = frappe.local.request.path or "/"
	if path.startswith(PASS_THROUGH):
		return
	conf = _site_config()
	info = conf.get("stemic_suspension") if isinstance(conf.get("stemic_suspension"), dict) else {}
	message = conf.get("stemic_suspended_message") or DEFAULT_MESSAGE
	contact = info.get("email") or conf.get("stemic_support_email") or "support@stemicschools.com"
	accept = frappe.get_request_header("Accept") or ""
	headers = {"Retry-After": "3600", "Cache-Control": "no-store"}
	if path.startswith("/api/") or "application/json" in accept:
		body = json.dumps({"exc_type": "SchoolSuspended", "message": message, "contact": contact,
						   **{k: info.get(k) for k in ("reason", "invoice", "amount_due", "due_date", "how_to_pay", "phone") if info.get(k)}})
		raise HTTPException(response=Response(body, status=503, mimetype="application/json", headers=headers))
	raise HTTPException(response=Response(page(info, message, contact), status=503, mimetype="text/html", headers=headers))


def _school() -> dict:
	"""The school's own name, crest, colour and office contacts for the paused page. Never required: any failure
	(no database, a half-installed site) gives {} and the page shows Stemic's details only."""
	try:
		if not getattr(frappe.local, "db", None):
			return {}
		get = lambda f: frappe.db.get_single_value("School Settings", f)  # noqa: E731
		return {k: (get(f) or "") for k, f in (("name", "school_name"), ("logo", "school_logo"), ("phone", "phone"),
											   ("email", "email"), ("color", "site_color"), ("accent", "statement_accent_color"))}
	except Exception:
		return {}


def page(info, message=DEFAULT_MESSAGE, contact="support@stemicschools.com", school=None):
	"""The paused page. Parents see the school's name and office contacts and that records are safe; Stemic's reason,
	the amount due, how to pay and who to call sit under "For school administrators"."""
	from school_erp.logic.website import initials, readable, tint

	esc = frappe.utils.escape_html
	sch = _school() if school is None else school
	brand = info.get("brand") or "Stemic Schools"
	name = info.get("school") or sch.get("name") or ""
	color = readable(sch.get("color") or sch.get("accent") or info.get("color") or "#166534")
	wash = tint(color, 0.92)
	if sch.get("logo"):
		crest = f'<img src="{esc(sch["logo"])}" alt="" style="height:64px;width:auto">'
	else:
		crest = (f'<svg width="58" height="64" viewBox="0 0 44 48" aria-hidden="true"><path d="M22 2 L40 8 V24 C40 35 32 43 22 46 '
				 f'C12 43 4 35 4 24 V8 Z" fill="{color}"/><text x="22" y="29" text-anchor="middle" font-family="sans-serif" '
				 f'font-weight="800" font-size="13" fill="#fff">{esc(initials(name or brand))}</text></svg>')
	office = []
	if sch.get("phone"):
		office.append(f'<a class="btn" href="tel:{esc(sch["phone"].replace(" ", ""))}">Call the school: {esc(sch["phone"])}</a>')
	if sch.get("email"):
		office.append(f'<a class="link" href="mailto:{esc(sch["email"])}">{esc(sch["email"])}</a>')
	office_html = "".join(office) or '<p class="muted">Please contact the school office.</p>'
	reason = (f'<div class="box"><div class="label">Reason</div><div>{esc(info["reason"])}</div></div>'
			  if info.get("reason") else "")
	owed = ""
	if info.get("amount_due"):
		owed = (f'<div class="box owed"><div class="label">Amount due</div><div class="amount">{esc(info["amount_due"])}</div>'
				f'<div class="muted">Invoice {esc(info.get("invoice", ""))}'
				f'{" &middot; was due " + esc(info["due_date"]) if info.get("due_date") else ""}</div></div>')
	pay = (f'<div class="box"><div class="label">How to pay</div><div>{esc(info["how_to_pay"])}</div></div>'
		   if info.get("how_to_pay") else "")
	phone = info.get("phone")
	call = f'<a class="btn ghost" href="tel:{esc(phone.replace(" ", ""))}">Call us</a>' if phone else ""
	since = f"Suspended since {esc(info['since'])}. " if info.get("since") else ""
	subject = esc(("Restore " + name) if name else "Suspended school")
	return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Portal paused - {esc(name or brand)}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{wash};font-family:Inter,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;line-height:1.55}}
.wrap{{max-width:580px;margin:0 auto;padding:56px 16px 32px;min-height:100vh;display:flex;flex-direction:column;justify-content:center}}
.card{{background:#fff;border:1px solid #e2e8f0;border-radius:24px;padding:44px 36px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:14px}}
.school{{font-weight:800;font-size:18px;color:#334155}}
h1{{font-size:28px;line-height:1.25;margin:4px 0 0}}
p{{margin:0}}
.lead{{font-size:17px;color:#475569}}
.office{{width:100%;display:flex;flex-direction:column;gap:10px;margin-top:8px}}
.btn{{display:flex;align-items:center;justify-content:center;min-height:50px;padding:0 18px;border-radius:12px;font-weight:700;
text-decoration:none;font-size:16px;background:{color};color:#fff;border:2px solid {color}}}
.btn.ghost{{background:#fff;color:#0f172a;border-color:#cbd5e1}}
.link{{color:#334155}}
details{{width:100%;border-top:1px solid #e2e8f0;padding-top:16px;margin-top:10px;text-align:left}}
summary{{cursor:pointer;font-weight:600;color:#334155;min-height:44px;display:flex;align-items:center;justify-content:center}}
.pill{{display:inline-block;background:#fdecea;color:#b42318;font-weight:700;font-size:12px;letter-spacing:.04em;
text-transform:uppercase;border-radius:999px;padding:4px 10px;margin:6px 0 4px}}
.box{{background:#f6f8fa;border-radius:10px;padding:12px 14px;margin:12px 0;font-size:15px}}
.box.owed{{background:#fff7f6}}
.label{{font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}}
.amount{{font-size:24px;font-weight:800}}
.muted{{color:#475569;font-size:14px}}
.actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}}
.actions .btn{{flex:1 1 140px;min-height:46px;font-size:15px}}
.foot{{text-align:center;color:#475569;font-size:13px;margin-top:18px}}
</style></head><body><div class="wrap"><div class="card">
{crest}
{f'<div class="school">{esc(name)}</div>' if name else ""}
<h1>The school portal is paused for now</h1>
<p class="lead">Your records are safe and nothing has been deleted. Parents and staff: please contact the school office
for fees, results or anything urgent.</p>
<div class="office">{office_html}</div>
<details><summary>For school administrators</summary>
<span class="pill">Service suspended</span>
<p>Signing in and all school work are paused until {esc(brand)} restores the service.</p>
{reason}{owed}{pay}
<p class="muted">Already paid or sorted it out? It can take a short while for {esc(brand)} to confirm and restore
the service. Contact us if it has not come back: <b>{esc(contact)}</b>{f" &middot; <b>{esc(phone)}</b>" if phone else ""}</p>
<div class="actions">
<a class="btn" href="mailto:{esc(contact)}?subject={subject}">Email us</a>
{call}
<a class="btn ghost" href="" onclick="location.reload();return false">Check again</a>
</div></details></div>
<div class="foot">{since}{esc(message) if not info.get("school") else ""} Powered by {esc(brand)}</div>
</div></body></html>"""
