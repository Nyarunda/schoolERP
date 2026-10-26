"""Finance runs on ERPNext's own accounting (suppliers, customers, invoices, payments, banking, reports).

School roles carry the ERPNext roles that open it, so a bursar never needs a separate accounts login:
	Bursar        -> Accounts User, Purchase Master Manager, Sales Master Manager
	School Admin  -> the same, plus Accounts Manager
The bank tools (reconciliation, statement import) are System Manager-only in ERPNext; finance staff get them too.
"""

import frappe

FINANCE_ROLES = {
	"Bursar": {"Accounts User", "Purchase Master Manager", "Sales Master Manager"},
	"School Admin": {"Accounts User", "Accounts Manager", "Purchase Master Manager", "Sales Master Manager"},
}
GRANTED = set().union(*FINANCE_ROLES.values())

# DocType -> {role: (read, write, create)}
BANK_TOOLS = {
	"Bank Reconciliation Tool": {"Accounts User": (1, 1, 1), "Accounts Manager": (1, 1, 1)},
	"Bank Statement Import": {"Accounts User": (1, 1, 1), "Accounts Manager": (1, 1, 1)},
	"Bank": {"Accounts User": (1, 0, 0), "Accounts Manager": (1, 1, 1)},
}


def needed(roles) -> set:
	return set().union(*(FINANCE_ROLES.get(r, set()) for r in roles))


def sync_user_roles(doc, method=None):
	"""User validate hook: add the ERPNext roles a school finance role needs; when a school finance role is taken away
	in this save, take away what only it had granted. Roles given some other way are never removed."""
	if doc.name in ("Administrator", "Guest") or not frappe.db.exists("DocType", "Account"):
		return
	roles = {r.role for r in doc.roles}
	want = needed(roles)
	for role in sorted(want - roles):
		if frappe.db.exists("Role", role):
			doc.append("roles", {"role": role})
	before = doc.get_doc_before_save()
	if before:
		dropped = needed({r.role for r in before.roles}) - want
		doc.set("roles", [r for r in doc.roles if r.role not in dropped])


def sync_all_users():
	for user in frappe.get_all("Has Role", filters={"role": ("in", list(FINANCE_ROLES)), "parenttype": "User"}, pluck="parent", distinct=True):
		doc = frappe.get_doc("User", user)
		missing = needed({r.role for r in doc.roles}) - {r.role for r in doc.roles}
		if missing and user not in ("Administrator", "Guest"):
			doc.add_roles(*[r for r in missing if frappe.db.exists("Role", r)])


def grant_bank_tools():
	from frappe.permissions import add_permission, update_permission_property

	for doctype, roles in BANK_TOOLS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role, (read, write, create) in roles.items():
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}):
				add_permission(doctype, role, 0)  # copies the standard permissions into Custom DocPerm first
			for ptype, value in (("read", read), ("write", write), ("create", create)):
				update_permission_property(doctype, role, 0, ptype, value, validate=False)


def setup_finance():
	grant_bank_tools()
	sync_all_users()
