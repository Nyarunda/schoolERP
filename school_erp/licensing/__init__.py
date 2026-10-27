"""License enforcement inside Frappe. Rules live in school_erp.logic.license."""

import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from school_erp.logic import license as lic

from .public_key import PUBLIC_KEY

CACHE_KEY = "school_erp:license_state"


def get_state(refresh: bool = False) -> dict:
	if not refresh:
		cached = frappe.cache.get_value(CACHE_KEY)
		if cached:
			return cached
	# Single DocTypes live in tabSingles, so check the DocType record rather than a table
	key = frappe.db.get_single_value("School Settings", "license_key") if frappe.db.exists("DocType", "School Settings") else None
	state = lic.evaluate(key or "", PUBLIC_KEY, getdate(nowdate()), site=frappe.local.site)
	frappe.cache.set_value(CACHE_KEY, state, expires_in_sec=6 * 3600)
	return state


def clear_cache():
	frappe.cache.delete_value(CACHE_KEY)


def is_enabled(module: str) -> bool:
	return module in get_state()["modules"]


def require(module: str, doctype: str | None = None):
	msg = lic.check(get_state(), module, doctype)
	if msg:
		frappe.throw(_(msg), title=_("Not in subscription"), exc=frappe.PermissionError)


def enforce_on_doc(doc, method=None):
	"""doc_events hook: block saving/submitting documents of modules the school has not licensed."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
		return
	module = lic.DOCTYPE_MODULE.get(doc.doctype)
	if module:
		require(module, doc.doctype)


def check_student_limit():
	state = get_state()
	limit = state.get("max_students") or 0
	if limit and frappe.db.count("Student", {"status": "Active"}) >= limit:
		frappe.throw(
			_("Your subscription allows {0} active students. Contact your vendor to raise the limit.").format(limit),
			title=_("Student limit reached"),
		)


def hidden_entities(state=None) -> dict[str, set[str]]:
	"""DocTypes and reports of modules the school has not licensed: not shown anywhere, and not readable."""
	doctypes = lic.hidden_doctypes((state or get_state())["modules"])
	reports = set(frappe.get_all("Report", filters={"ref_doctype": ("in", list(doctypes))}, pluck="name")) if doctypes else set()
	return {"DocType": doctypes, "Report": reports}


def _hidden(doctype) -> bool:
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
		return False
	return doctype in lic.hidden_doctypes(get_state()["modules"])


def licensed_read(doc, ptype=None, user=None, debug=False):
	"""has_permission hook: nobody opens, reads or prints a record of a module the school has not licensed.
	A hook can only deny (True means "no objection"), so the DocType's other rules still decide otherwise."""
	return not _hidden(doc.doctype)


def licensed_query(user=None, doctype=None):
	"""permission_query_conditions hook (Frappe passes the DocType): lists, reports and search of an unlicensed
	module's DocType come back empty."""
	return "1=0" if doctype and _hidden(doctype) else ""


USER_LISTS = ("can_read", "can_write", "can_create", "can_delete", "can_submit", "can_cancel", "can_search",
			  "can_get_report", "can_select", "can_export", "can_import", "can_print", "can_email", "can_set_user_permissions")


def boot_session(bootinfo):
	if frappe.session.user == "Guest":
		return
	state = get_state()
	hidden = hidden_entities(state)
	# The desk (search bar, list routes, link fields) learns what the user may open from these lists
	user = bootinfo.get("user") or {}
	for key in USER_LISTS:
		if isinstance(user.get(key), list):
			user[key] = [dt for dt in user[key] if dt not in hidden["DocType"]]
	bootinfo.school_erp = {
		"modules": state["modules"],
		"status": state["status"],
		"message": state["message"],
		"days_left": state["days_left"],
		"hidden_doctypes": sorted(hidden["DocType"]),
		"hidden_reports": sorted(hidden["Report"]),
	}
	if hidden["DocType"]:
		_drop_hidden_blocks(bootinfo, hidden)


# A workspace's layout names its widgets; drop the ones get_desktop_page leaves out so no empty slot remains
LAYOUT_KEYS = {"card": "card_name", "shortcut": "shortcut_name", "chart": "chart_name", "number_card": "number_card_name"}


def _hidden_widgets(workspace, hidden) -> dict[str, set[str]]:
	doc = frappe.get_cached_doc("Workspace", workspace)
	gone = {"card": set(), "shortcut": set(), "chart": set(), "number_card": set()}
	card, links = None, []
	for row in [*doc.links, None]:
		if row is None or row.type == "Card Break":
			if card and links and all(link.link_to in hidden.get(link.link_type, ()) for link in links):
				gone["card"].add(card)
			card, links = (row.label if row else None), []
		else:
			links.append(row)
	gone["shortcut"] = {s.label for s in doc.shortcuts if s.link_to in hidden.get(s.type, ())}
	for c in doc.charts:
		if frappe.db.get_value("Dashboard Chart", c.chart_name, "document_type", cache=True) in hidden["DocType"]:
			gone["chart"].add(c.chart_name)
	for c in doc.number_cards:
		if frappe.db.get_value("Number Card", c.number_card_name, "document_type", cache=True) in hidden["DocType"]:
			gone["number_card"].add(c.number_card_name)
	return gone


def _drop_hidden_blocks(bootinfo, hidden):
	for page in (bootinfo.get("workspaces") or {}).get("pages") or []:
		if page.get("module") != "School" or not isinstance(page.get("content"), str):
			continue
		gone = _hidden_widgets(page["name"], hidden)
		if not any(gone.values()):
			continue
		blocks = json.loads(page["content"] or "[]")
		page["content"] = json.dumps(
			[b for b in blocks if (b.get("data") or {}).get(LAYOUT_KEYS.get(b.get("type"), "")) not in gone.get(b.get("type"), ())]
		)


@frappe.whitelist()
def get_desktop_page(page):
	"""frappe.desk.desktop.get_desktop_page without links, shortcuts, charts and number cards of unlicensed modules."""
	from frappe.desk.desktop import get_desktop_page as standard

	data = standard(page)
	hidden = hidden_entities()
	if not data or not hidden["DocType"]:
		return data

	def shown(link_type, link_to):
		return link_to not in hidden.get(link_type, ())

	def source_shown(doctype, name):
		return frappe.db.get_value(doctype, name, "document_type", cache=True) not in hidden["DocType"]

	cards = []
	for card in data["cards"]["items"]:
		card["links"] = [link for link in card.get("links", []) if shown(link.get("link_type"), link.get("link_to"))]
		if card["links"]:
			cards.append(card)
	data["cards"]["items"] = cards
	data["shortcuts"]["items"] = [s for s in data["shortcuts"]["items"] if shown(s.get("type"), s.get("link_to"))]
	data["charts"]["items"] = [c for c in data["charts"]["items"] if source_shown("Dashboard Chart", c.get("chart_name"))]
	data["number_cards"]["items"] = [
		c for c in data["number_cards"]["items"] if source_shown("Number Card", c.get("number_card_name"))
	]
	return data


def daily_license_check():
	get_state(refresh=True)


@frappe.whitelist()
def license_overview():
	"""Everything the License tab in School Settings shows: the saved key's state, usage and the full module list."""
	frappe.has_permission("School Settings", "read", throw=True)
	state = get_state()
	return {
		**state,
		"this_site": frappe.local.site,
		"active_students": frappe.db.count("Student", {"status": "Active"}),
		"catalogue": [{"code": code, "label": label, "included": code in state["modules"]} for code, label in lic.MODULES.items()],
	}
