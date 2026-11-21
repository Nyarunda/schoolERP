"""Start posting pocket money, unmatched M-Pesa, library fines and fuel to the General Ledger.

1. Create the ledger accounts (and the Fuel expense category).
2. Bring existing pocket money balances in with one opening entry, and mark when posting started.
3. Put M-Pesa payments already waiting (Unmatched / Failed) into Unidentified Receipts.

A problem (closed period, odd chart of accounts) is logged, never stops migrate; School Settings > Check Ledger then
shows what is still to post."""

import frappe


def execute():
	settings = frappe.get_single("School Settings")
	if not settings.company:
		return
	from school_erp.api import ledger

	for step, name in ((_accounts, "accounts"), (_opening, "pocket money opening entry"), (_suspense, "M-Pesa suspense")):
		try:
			step(ledger)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Money-through-ledger patch: {name} not done")


def _accounts(ledger):
	ledger.ensure_accounts(frappe.get_single("School Settings"), save=True)


def _opening(ledger):
	ledger.post_pocket_money_opening()


def _suspense(ledger):
	for name in frappe.get_all("M-Pesa Transaction", filters={"status": ("in", ["Unmatched", "Failed"]), "amount": (">", 0),
														   "suspense_entry": ("is", "not set")}, pluck="name"):
		ledger.post_suspense(frappe.get_doc("M-Pesa Transaction", name))
