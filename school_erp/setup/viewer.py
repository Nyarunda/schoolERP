"""School Viewer: a read-only role. It opens, searches, prints and runs reports on everything the school has licensed,
and creates, changes, submits, cancels or deletes nothing. For auditors, board members, owners and inspectors.

School ERP's own doctypes, reports and pages carry the role in their own definitions. ERPNext's finance and stores
screens and reports get it here (Custom DocPerm and Custom Role), read-only. Note for ERPNext doctypes: once a
doctype has custom permissions Frappe uses only those, so this list is kept to what a viewer needs.
"""

import frappe

ROLE = "School Viewer"
READ_ONLY = ("read", "report", "print")
MODIFY = ("write", "create", "delete", "submit", "cancel", "amend", "import", "share")

ERP_DOCTYPES = [
	"Company", "Fiscal Year", "Account", "Cost Center", "GL Entry", "Journal Entry", "Customer", "Supplier",
	"Sales Invoice", "Payment Entry", "Purchase Invoice", "Purchase Order", "Purchase Receipt", "Mode of Payment",
	"Item", "Item Group", "Warehouse", "Stock Entry", "Stock Ledger Entry", "Bin",
]
ERP_REPORTS = [
	"General Ledger", "Trial Balance", "Profit and Loss Statement", "Balance Sheet", "Cash Flow",
	"Accounts Receivable", "Accounts Payable", "Stock Balance", "Stock Ledger", "Stock Projected Qty",
]


def setup():
	"""Idempotent (after_install, after_migrate)."""
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	if not frappe.db.exists("DocType", "Account"):  # ERPNext not installed
		return
	from frappe.permissions import add_permission, update_permission_property

	for doctype in ERP_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": ROLE, "permlevel": 0, "if_owner": 0}):
			add_permission(doctype, ROLE, 0)  # copies the standard permissions into Custom DocPerm first
		for ptype in READ_ONLY:
			update_permission_property(doctype, ROLE, 0, ptype, 1, validate=False)
		for ptype in MODIFY:  # never anything that changes data, even if a row was edited by hand
			update_permission_property(doctype, ROLE, 0, ptype, 0, validate=False)
	for report in ERP_REPORTS:
		if not frappe.db.exists("Report", report):
			continue
		name = frappe.db.get_value("Custom Role", {"report": report})
		doc = frappe.get_doc("Custom Role", name) if name else frappe.get_doc({
			"doctype": "Custom Role", "report": report,
			"roles": [{"role": r} for r in frappe.get_all("Has Role", filters={"parent": report, "parenttype": "Report"},
														 pluck="role")]})
		if ROLE not in {r.role for r in doc.roles}:
			doc.append("roles", {"role": ROLE})
			doc.flags.ignore_permissions = True
			doc.save()
	frappe.clear_cache()
