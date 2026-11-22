"""Schools with several branches, each its own site, grouped for billing and reporting.

- Cost centers in Stemic's books: every school has one; a group's branches sit under the group's cost center, other
  schools under "Schools". Invoices, payments, commissions, credit notes and expenses for a school carry it, so Profit and
  Loss runs per school, per branch and per group.
- Billing: "One combined bill" sends the branches' invoice emails to the head office, gives one statement for all branches
  and lets one payment settle them (oldest first); each branch keeps its own invoice and balance. "Each branch billed
  separately" changes nothing.
"""

import frappe
from frappe.utils import flt, getdate, nowdate

from stemic_control import accounting

COMBINED = "One combined bill"
BILLING_EVENTS = ("Invoice Issued", "Payment Received", "Invoice Overdue", "Trial Ending")
SCHOOLS_GROUP = "Schools"


# ----------------------------------------------------------------------------- cost centers
def _root(company):
	root = frappe.db.get_value("Cost Center", {"company": company, "is_group": 1, "parent_cost_center": ("in", ["", None])}, "name")
	if not root:
		frappe.throw(f"{company} has no root cost center", frappe.ValidationError)
	return root


def _ensure_center(company, label, parent, is_group):
	existing = frappe.db.get_value("Cost Center", {"company": company, "cost_center_name": label}, ["name", "parent_cost_center", "is_group"],
								   as_dict=True)
	if existing:
		if existing.parent_cost_center != parent:
			doc = frappe.get_doc("Cost Center", existing.name)
			doc.parent_cost_center = parent
			doc.flags.ignore_permissions = True
			doc.save()
		return existing.name
	doc = frappe.get_doc({"doctype": "Cost Center", "cost_center_name": label, "parent_cost_center": parent,
						  "company": company, "is_group": int(is_group)})
	doc.flags.ignore_permissions = True
	return doc.insert().name


def group_center(company, group):
	return _ensure_center(company, f"Group - {group}", _root(company), True)


def cost_center(tenant):
	"""The school's cost center (created on first use, and moved when the school joins or leaves a group)."""
	if not accounting.enabled():
		return None
	company = accounting.company()
	t = frappe.db.get_value("SaaS Tenant", tenant, ["school_name", "school_group", "branch_name", "name"], as_dict=True)
	if not t:
		return frappe.get_cached_value("Company", company, "cost_center")
	parent = group_center(company, t.school_group) if t.school_group else _ensure_center(company, SCHOOLS_GROUP, _root(company), True)
	label = f"{t.school_name or t.name}" + (f" - {t.branch_name}" if t.school_group and t.branch_name else "") + f" ({t.name})"
	existing = frappe.db.get_value("SaaS Tenant", tenant, "cost_center")
	if existing and frappe.db.exists("Cost Center", existing):
		if frappe.db.get_value("Cost Center", existing, "parent_cost_center") != parent:
			doc = frappe.get_doc("Cost Center", existing)
			doc.parent_cost_center = parent
			doc.flags.ignore_permissions = True
			doc.save()
		return existing
	name = _ensure_center(company, label, parent, False)
	frappe.db.set_value("SaaS Tenant", tenant, "cost_center", name, update_modified=False)
	return name


def sync_cost_centers(group):
	"""After a group is saved: its cost center, and its branches under it."""
	if not accounting.enabled():
		return
	company = accounting.company()
	frappe.db.set_value("SaaS School Group", group, "cost_center", group_center(company, group), update_modified=False)
	for tenant in frappe.get_all("SaaS Tenant", filters={"school_group": group}, pluck="name"):
		cost_center(tenant)


def on_tenant_update(doc, method=None):
	"""SaaS Tenant saved: keep its cost center under the right group."""
	before = doc.get_doc_before_save()
	if accounting.enabled() and (not doc.cost_center or (before and (before.school_group != doc.school_group
																		 or before.branch_name != doc.branch_name))):
		try:
			cost_center(doc.name)
		except Exception:
			frappe.log_error(title=f"Cost center for {doc.name} not updated")


# ----------------------------------------------------------------------------- billing
def billing_email(tenant, event):
	"""Where a school's billing emails go: the head office for a combined group, else None (the school)."""
	if event not in BILLING_EVENTS:
		return None
	group = frappe.db.get_value("SaaS Tenant", tenant, "school_group")
	if not group:
		return None
	g = frappe.db.get_value("SaaS School Group", group, ["billing_mode", "billing_email"], as_dict=True)
	return g.billing_email if g and g.billing_mode == COMBINED and g.billing_email else None


def _admin():
	accounting._admin()


@frappe.whitelist(methods=["GET"])
def group_overview(group):
	"""The group's branches with their site, status, plan, students licensed and what each owes; and the open invoices."""
	_admin()
	branches = frappe.get_all("SaaS Tenant", filters={"school_group": group}, order_by="school_name asc",
							  fields=["name", "school_name", "branch_name", "status", "canonical_site", "cost_center"])
	invoices = statement_rows(group)
	for b in branches:
		b.plan = frappe.db.get_value("SaaS Subscription", {"tenant": b.name, "status": ("!=", "Cancelled")}, "plan")
		b.owed = flt(sum(flt(i.outstanding) for i in invoices if i.tenant == b.name), 2)
	g = frappe.get_doc("SaaS School Group", group)
	return {"group": g.name, "billing_mode": g.billing_mode, "billing_email": g.billing_email, "branches": branches,
			"invoices": invoices, "owed": flt(sum(flt(i.outstanding) for i in invoices), 2)}


def statement_rows(group):
	return frappe.db.sql("""select i.name, i.tenant, t.school_name, t.branch_name, i.issue_date, i.due_date, i.plan, i.total,
		i.paid_amount, i.credited_amount, i.outstanding, i.status, i.currency
		from `tabSaaS Invoice` i join `tabSaaS Tenant` t on t.name = i.tenant
		where t.school_group = %s and i.docstatus = 1 and i.outstanding > 0
		order by i.due_date asc, i.issue_date asc, i.creation asc""", group, as_dict=True)


@frappe.whitelist(methods=["POST"])
def email_statement(group):
	"""One statement for all branches, emailed to the head office."""
	_admin()
	from stemic_control import communications

	g = frappe.get_doc("SaaS School Group", group)
	if not g.billing_email:
		frappe.throw("Enter the head office billing email first", frappe.ValidationError)
	rows = statement_rows(group)
	total = flt(sum(flt(r.outstanding) for r in rows), 2)
	cur = rows[0].currency if rows else "KES"
	lines = [(f"{r.school_name}{' - ' + r.branch_name if r.branch_name else ''}: {r.name} (due {r.due_date})",
			  communications._money(r.outstanding, r.currency)) for r in rows]
	html = communications.email_html(f"{g.group_name}: statement", f"What is owed across your branches on {getdate(nowdate())}.",
									 rows=lines + [("Total", communications._money(total, cur))],
									 blocks=[communications.how_to_pay()] if rows else ())
	frappe.sendmail(recipients=[g.billing_email], subject=f"{g.group_name}: statement, {communications._money(total, cur)} owed",
					message=html, reference_doctype="SaaS School Group", reference_name=g.name, now=bool(frappe.flags.in_test))
	return {"sent_to": g.billing_email, "invoices": len(rows), "total": total}


@frappe.whitelist(methods=["POST"])
def record_group_payment(group, amount, mode, reference, payment_date=None):
	"""One payment from the head office, spread over the branches' open invoices, oldest due first. Each part is a normal
	SaaS Payment (posted to the books with the branch's cost center); references get /1, /2... when split."""
	_admin()
	from stemic_control import billing

	amount = flt(amount, 2)
	reference = (reference or "").strip().upper()
	if amount <= 0 or not reference:
		frappe.throw("Enter the amount and the payment reference", frappe.ValidationError)
	rows = statement_rows(group)
	owed = flt(sum(flt(r.outstanding) for r in rows), 2)
	if amount > owed + 0.005:
		frappe.throw(f"That is more than the {owed:,.2f} the group owes", frappe.ValidationError)
	parts, left = [], amount
	for r in rows:
		if left <= 0:
			break
		take = flt(min(left, flt(r.outstanding)), 2)
		parts.append((r.name, take))
		left = flt(left - take, 2)
	made = []
	for n, (invoice, take) in enumerate(parts, 1):
		ref = reference if len(parts) == 1 else f"{reference}/{n}"
		made.append(billing.record_payment(invoice, take, mode, ref, payment_date=payment_date or nowdate(),
										   notes=f"Part of {group} payment {reference}")["payment"])
	return {"payments": made, "allocated": [{"invoice": i, "amount": a} for i, a in parts]}
