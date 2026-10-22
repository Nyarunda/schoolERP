"""Frappe Workflows for School approvals (leave, expenses).

Created/updated on install, migrate, Run School Setup and when the approver roles in School Settings change.
The approval buttons, allowed roles, states and audit trail are Frappe's standard Workflow engine;
the app adds notifications (bell, email, toast, SMS) when a document enters a new state.
"""

import frappe

STATE_STYLE = {
	"Draft": "", "Pending Approval": "Warning", "Pending Final Approval": "Warning",
	"Approved": "Success", "Rejected": "Danger", "Cancelled": "Inverse",
}
ACTIONS = ["Send for Approval", "Approve", "Reject", "Resend", "Cancel"]
STAFF_EDITORS = ["Staff", "Teacher", "Driver", "Bursar", "Head Teacher", "School Admin", "Transport Manager"]


def _ensure_masters():
	for state, style in STATE_STYLE.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(ignore_permissions=True)
	for action in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(ignore_permissions=True)


def _roles_exist(*roles):
	return [r for r in roles if r and frappe.db.exists("Role", r)]


def leave_workflow():
	states = []
	for role in _roles_exist(*STAFF_EDITORS, "Leave Approver"):
		states.append({"state": "Pending Approval", "doc_status": "0", "allow_edit": role})
	states += [
		{"state": "Approved", "doc_status": "1", "allow_edit": "Head Teacher"},
		{"state": "Rejected", "doc_status": "1", "allow_edit": "Head Teacher"},
		{"state": "Cancelled", "doc_status": "2", "allow_edit": "Head Teacher"},
	]
	own_approver = "doc.approver == frappe.session.user"
	transitions = [
		# the staff member's own approver (their 'Reports To', or the Head Teacher set in School Settings)
		{"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Leave Approver", "condition": own_approver, "allow_self_approval": 0},
		{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Leave Approver", "condition": own_approver, "allow_self_approval": 0},
		# the Head Teacher can decide any leave (including their own, when nobody is above them)
		{"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Head Teacher", "allow_self_approval": 1},
		{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Head Teacher", "allow_self_approval": 1},
		{"state": "Approved", "action": "Cancel", "next_state": "Cancelled", "allowed": "Head Teacher", "allow_self_approval": 1},
		{"state": "Approved", "action": "Cancel", "next_state": "Cancelled", "allowed": "Leave Approver", "condition": own_approver, "allow_self_approval": 0},
	]
	return {"workflow_name": "School Leave Approval", "document_type": "Leave Application", "states": states, "transitions": transitions}


def expense_workflow():
	s = frappe.get_cached_doc("School Settings")
	first = s.expense_first_approver_role or "Bursar"
	final = s.expense_final_approver_role or "Head Teacher"
	states = []
	for role in _roles_exist(*STAFF_EDITORS):
		states.append({"state": "Draft", "doc_status": "0", "allow_edit": role})
	states += [{"state": "Pending Approval", "doc_status": "0", "allow_edit": first}]
	states += [{"state": "Pending Final Approval", "doc_status": "0", "allow_edit": final}]
	for role in _roles_exist(*STAFF_EDITORS):
		states.append({"state": "Rejected", "doc_status": "0", "allow_edit": role})
	states += [
		{"state": "Approved", "doc_status": "1", "allow_edit": first},
		{"state": "Cancelled", "doc_status": "2", "allow_edit": first},
	]
	transitions = []
	for role in _roles_exist(*STAFF_EDITORS):
		transitions.append({"state": "Draft", "action": "Send for Approval", "next_state": "Pending Approval", "allowed": role, "allow_self_approval": 1})
		transitions.append({"state": "Rejected", "action": "Resend", "next_state": "Pending Approval", "allowed": role, "allow_self_approval": 1})
	transitions += [
		# nobody approves their own expense (allow_self_approval = 0)
		{"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": first, "condition": "doc.levels_required == 1", "allow_self_approval": 0},
		{"state": "Pending Approval", "action": "Approve", "next_state": "Pending Final Approval", "allowed": first, "condition": "doc.levels_required >= 2", "allow_self_approval": 0},
		{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": first, "allow_self_approval": 0},
		{"state": "Pending Final Approval", "action": "Approve", "next_state": "Approved", "allowed": final, "allow_self_approval": 0},
		{"state": "Pending Final Approval", "action": "Reject", "next_state": "Rejected", "allowed": final, "allow_self_approval": 0},
		{"state": "Approved", "action": "Cancel", "next_state": "Cancelled", "allowed": first, "allow_self_approval": 1},
		{"state": "Approved", "action": "Cancel", "next_state": "Cancelled", "allowed": final, "allow_self_approval": 1},
	]
	return {"workflow_name": "School Expense Approval", "document_type": "School Expense", "states": states, "transitions": transitions}


def make_workflows():
	if not frappe.db.exists("DocType", "Leave Application"):
		return
	_ensure_masters()
	for spec in (leave_workflow(), expense_workflow()):
		name = spec["workflow_name"]
		exists = frappe.db.exists("Workflow", name)
		if exists and not frappe.db.get_value("Workflow", name, "is_active"):
			continue  # a school deliberately switched it off: leave it alone
		doc = frappe.get_doc("Workflow", name) if exists else frappe.new_doc("Workflow")
		doc.update({
			"workflow_name": name, "document_type": spec["document_type"], "is_active": 1,
			"workflow_state_field": "status", "override_status": 1, "send_email_alert": 0,
		})
		doc.set("states", spec["states"])
		doc.set("transitions", spec["transitions"])
		doc.flags.ignore_permissions = True
		doc.save()
	frappe.clear_cache()


def sync_leave_approvers():
	"""Everyone who approves someone's leave (a 'Reports To', or the Head Teacher login) gets the Leave Approver role."""
	users = set(frappe.db.sql_list(
		"""select distinct boss.user from `tabStaff Member` sm join `tabStaff Member` boss on boss.name = sm.reports_to
		where ifnull(boss.user, '') != '' and sm.status != 'Left'"""))
	head = frappe.db.get_single_value("School Settings", "head_teacher_user")
	if head:
		users.add(head)
	for u in users:
		if u not in ("Administrator", "Guest") and "Leave Approver" not in frappe.get_roles(u):
			user = frappe.get_doc("User", u)
			user.flags.ignore_permissions = True
			user.add_roles("Leave Approver")


REASON_FIELD = {"Leave Application": "decision_comment", "School Expense": "rejection_reason"}


@frappe.whitelist()
def save_rejection_reason(doctype, name, reason):
	"""Store the reason just before the Workflow 'Reject' action runs (apply_workflow reloads the document
	from the database, so an unsaved reason would be lost). Only someone who may reject can call it."""
	from frappe.model.workflow import get_transitions

	field = REASON_FIELD.get(doctype)
	if not field:
		frappe.throw("Not supported")
	doc = frappe.get_doc(doctype, name)
	if not any(t.action == "Reject" for t in get_transitions(doc)):
		frappe.throw(frappe._("You cannot reject this document"), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(frappe._("Give a reason"))
	doc.db_set(field, reason)
	return True
