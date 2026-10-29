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
	message = conf.get("stemic_suspended_message") or DEFAULT_MESSAGE
	contact = conf.get("stemic_support_email") or "support@stemicschools.com"
	accept = frappe.get_request_header("Accept") or ""
	headers = {"Retry-After": "3600", "Cache-Control": "no-store"}
	if path.startswith("/api/") or "application/json" in accept:
		body = json.dumps({"exc_type": "SchoolSuspended", "message": message, "contact": contact})
		raise HTTPException(response=Response(body, status=503, mimetype="application/json", headers=headers))
	raise HTTPException(response=Response(_page(message, contact), status=503, mimetype="text/html", headers=headers))


def _page(message, contact):
	esc = frappe.utils.escape_html
	return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Service suspended</title>
<style>
body{{margin:0;background:#f4f7fb;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#14243d}}
.card{{max-width:520px;margin:12vh auto 0;background:#fff;border:1px solid #e1e7f0;border-radius:10px;overflow:hidden}}
.band{{background:#1b3a6b;color:#fff;font-weight:700;font-size:18px;padding:16px 24px}}.band span{{color:#8fd694}}
.body{{padding:24px}}h1{{font-size:21px;margin:0 0 10px}}p{{line-height:1.55;margin:0 0 12px}}a{{color:#1b3a6b;font-weight:600}}
</style></head><body><div class="card"><div class="band">Stemic <span>Schools</span></div><div class="body">
<h1>Service suspended</h1><p>{esc(message)}</p>
<p>Contact <a href="mailto:{esc(contact)}">{esc(contact)}</a>.</p></div></div></body></html>"""
