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


PAUSE = ('<svg width="44" height="44" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="11" '
		 'fill="currentColor" opacity=".12"/><rect x="8.2" y="7" width="2.6" height="10" rx="1.1" fill="currentColor"/>'
		 '<rect x="13.2" y="7" width="2.6" height="10" rx="1.1" fill="currentColor"/></svg>')


def page(info, message=DEFAULT_MESSAGE, contact="support@stemicschools.com"):
	"""The suspended page: who, why, what is owed and how to pay, how to reach Stemic, and a way to check again."""
	esc = frappe.utils.escape_html
	brand = info.get("brand") or "Stemic Schools"
	color, accent = info.get("color") or "#1b3a6b", info.get("accent") or "#43a047"
	school = info.get("school") or ""
	first, _, rest = brand.partition(" ")
	heading = f"{esc(school)}'s service is suspended" if school else "This school's service is suspended"
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
	intro = ("Signing in and all school work are paused until the service is restored. Your school's records are "
			 "safe and nothing has been deleted.")
	return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Service suspended - {esc(school or brand)}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f4f7fb;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#14243d;line-height:1.55}}
.wrap{{max-width:560px;margin:0 auto;padding:32px 16px}}
.card{{background:#fff;border:1px solid #e1e7f0;border-radius:12px;overflow:hidden;box-shadow:0 6px 24px rgba(20,36,61,.06)}}
.band{{background:{color};color:#fff;font-weight:700;font-size:18px;padding:16px 24px}}.band span{{opacity:.75}}
.body{{padding:26px 24px 28px}}
.status{{display:flex;align-items:center;gap:14px;color:#c62828;margin-bottom:8px}}
.pill{{display:inline-block;background:#fdecea;color:#c62828;font-weight:700;font-size:12px;letter-spacing:.04em;
text-transform:uppercase;border-radius:999px;padding:4px 10px}}
h1{{font-size:22px;line-height:1.3;margin:4px 0 0;color:#14243d}}
p{{margin:12px 0}}
.box{{background:#f6f8fa;border-left:4px solid {accent};border-radius:8px;padding:12px 14px;margin:14px 0;font-size:15px}}
.box.owed{{border-left-color:#c62828;background:#fff7f6}}
.label{{font-size:12px;font-weight:700;color:#5b6b82;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}}
.amount{{font-size:24px;font-weight:800;color:#14243d}}
.muted{{color:#5b6b82;font-size:14px}}
.actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}}
.btn{{display:inline-block;padding:11px 18px;border-radius:8px;font-weight:700;text-decoration:none;font-size:15px;
background:{accent};color:#fff;border:2px solid {accent}}}
.btn.ghost{{background:#fff;color:{color};border-color:#d5dde8}}
.foot{{text-align:center;color:#5b6b82;font-size:13px;margin-top:16px}}
</style></head><body><div class="wrap"><div class="card">
<div class="band">{esc(first)}{f" <span>{esc(rest)}</span>" if rest else ""}</div>
<div class="body">
<div class="status">{PAUSE}<div><span class="pill">Service suspended</span><h1>{heading}</h1></div></div>
<p>{intro}</p>
{reason}{owed}{pay}
<p class="muted">Already paid or sorted it out? It can take a short while for {esc(brand)} to confirm and restore
the service. Contact us if it has not come back: <b>{esc(contact)}</b>{f" &middot; <b>{esc(phone)}</b>" if phone else ""}</p>
<div class="actions">
<a class="btn" href="mailto:{esc(contact)}?subject={esc(("Restore " + school) if school else "Suspended school")}">Email us</a>
{call}
<a class="btn ghost" href="" onclick="location.reload();return false">Check again</a>
</div></div></div>
<div class="foot">{since}{esc(message) if not school else ""}</div>
</div></body></html>"""
