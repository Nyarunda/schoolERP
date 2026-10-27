"""Staff: leave balances and decisions, duty reports, staff status."""

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, get_time, getdate, now_datetime, nowdate

from school_erp import licensing
from school_erp.api.notify import notify, staff_for_user, users_for_role
from school_erp.logic.operations import leave_days

MANAGER_ROLES = {"System Manager", "School Admin", "Head Teacher"}


def is_manager(user=None) -> bool:
	return bool(set(frappe.get_roles(user or frappe.session.user)) & MANAGER_ROLES)


def head_teacher_users() -> list[str]:
	user = frappe.db.get_single_value("School Settings", "head_teacher_user")
	return [user] if user else users_for_role("Head Teacher")


# ----------------------------------------------------------------------------- leave
def holidays_between(from_date, to_date) -> set:
	company = frappe.db.get_single_value("School Settings", "company")
	hl = frappe.db.get_value("Company", company, "default_holiday_list") if company else None
	if not hl:
		return set()
	return {
		getdate(d)
		for d in frappe.get_all(
			"Holiday", filters={"parent": hl, "holiday_date": ("between", [from_date, to_date])}, pluck="holiday_date"
		)
	}


def count_days(leave_type: str, from_date, to_date) -> float:
	include = frappe.db.get_value("Leave Type", leave_type, "include_weekends")
	f, t = getdate(from_date), getdate(to_date)
	return leave_days(f, t, bool(include), set() if include else holidays_between(f, t))


def days_taken(staff_member, leave_type, year, exclude=None) -> float:
	rows = frappe.db.sql(
		"""select coalesce(sum(total_days), 0) from `tabLeave Application`
		where staff_member=%s and leave_type=%s and year(from_date)=%s
		  and docstatus < 2 and status in ('Pending Approval', 'Approved') and name != %s""",
		(staff_member, leave_type, year, exclude or ""),
	)
	return float(rows[0][0] or 0)


@frappe.whitelist()
@licensing.licensed("Leave Application")
def leave_balances(staff_member, year=None):
	"""Entitled / taken / pending / remaining per leave type, for the form and reports."""
	year = int(year or getdate(nowdate()).year)
	out = []
	for lt in frappe.get_all("Leave Type", fields=["name", "days_per_year"], order_by="name"):
		taken = frappe.db.sql(
			"""select
				coalesce(sum(case when status='Approved' then total_days end), 0),
				coalesce(sum(case when status='Pending Approval' then total_days end), 0)
			from `tabLeave Application`
			where staff_member=%s and leave_type=%s and year(from_date)=%s and docstatus < 2""",
			(staff_member, lt.name, year),
		)[0]
		entitled = lt.days_per_year or 0
		out.append({
			"leave_type": lt.name,
			"entitled": entitled,
			"taken": float(taken[0]),
			"pending": float(taken[1]),
			"balance": (entitled - float(taken[0]) - float(taken[1])) if entitled else None,
		})
	return out


def approver_for(staff_member) -> str | None:
	boss = frappe.db.get_value("Staff Member", staff_member, "reports_to")
	if boss:
		user = frappe.db.get_value("Staff Member", boss, "user")
		if user:
			return user
	heads = head_teacher_users()
	return heads[0] if heads else None


def can_decide(doc, user=None) -> bool:
	user = user or frappe.session.user
	return user == doc.approver or is_manager(user)


@frappe.whitelist()
def decide_leave(name, decision, comment=None):
	"""Approve/Reject through the Frappe Workflow (same rules as the Actions menu on the form)."""
	from frappe.model.workflow import apply_workflow

	licensing.require("staff")
	if decision not in ("Approved", "Rejected"):
		frappe.throw(_("Unknown decision"))
	doc = frappe.get_doc("Leave Application", name)
	if doc.docstatus != 0 or doc.status != "Pending Approval":
		frappe.throw(_("This application has already been decided ({0})").format(doc.status))
	if comment:
		doc.db_set("decision_comment", comment)  # apply_workflow reloads the doc from the database
	doc = apply_workflow(doc, "Approve" if decision == "Approved" else "Reject")
	return doc.status


def _period(doc):
	f, t = formatdate(doc.from_date, "d MMM"), formatdate(doc.to_date, "d MMM yyyy")
	return f if doc.from_date == doc.to_date else f"{f} - {t}"


def notify_leave_decision(doc):
	period = _period(doc)
	if doc.status == "Approved":
		notify(
			_("Leave approved: {0}, {1}").format(doc.leave_type, period),
			_("Your {0} ({1} day(s)) for {2} has been approved.{3}").format(
				doc.leave_type, doc.total_days, period,
				f" Your reliever is {doc.reliever_name}." if doc.reliever else ""),
			staff=[doc.staff_member], doc=doc, indicator="green",
			sms_text=f"Your {doc.leave_type} for {period} has been APPROVED." + (f" Reliever: {doc.reliever_name}." if doc.reliever else ""),
		)
		if doc.reliever:
			notify(
				_("You are relieving {0}, {1}").format(doc.staff_name, period),
				_("{0} will be on {1} for {2}. You have been assigned as their reliever; please take over their lessons and duties.").format(
					doc.staff_name, doc.leave_type, period),
				staff=[doc.reliever], doc=doc,
				sms_text=f"You will relieve {doc.staff_name} ({doc.leave_type}) for {period}. Please take over their lessons and duties.",
			)
	else:
		notify(
			_("Leave not approved: {0}, {1}").format(doc.leave_type, period),
			_("Your {0} for {1} was not approved. Reason: {2}").format(doc.leave_type, period, doc.decision_comment or "-"),
			staff=[doc.staff_member], doc=doc, indicator="red",
			sms_text=f"Your {doc.leave_type} for {period} was NOT approved. Reason: {doc.decision_comment or '-'}",
		)


def update_staff_leave_status():
	"""Daily: mark staff On Leave / back to Active from approved leave."""
	if not licensing.is_enabled("staff"):
		return
	today = nowdate()
	away = set(frappe.get_all(
		"Leave Application",
		filters={"docstatus": 1, "status": "Approved", "from_date": ("<=", today), "to_date": (">=", today)},
		pluck="staff_member",
	))
	for s in away:
		frappe.db.set_value("Staff Member", s, "status", "On Leave", update_modified=False)
	for s in frappe.get_all("Staff Member", filters={"status": "On Leave"}, pluck="name"):
		if s not in away:
			frappe.db.set_value("Staff Member", s, "status", "Active", update_modified=False)


# ----------------------------------------------------------------------------- duty
def on_duty_today(date=None) -> list[str]:
	date = date or nowdate()
	return frappe.db.sql_list(
		"""select distinct m.staff_member from `tabDuty Roster Member` m
		join `tabDuty Roster` r on r.name = m.parent
		where %s between r.from_date and r.to_date and m.duty_role = 'Teacher on Duty'""",
		date,
	)


def alert_missing_duty_reports():
	"""After the due time, remind today's teacher(s) on duty once, and tell the Head Teacher."""
	if not licensing.is_enabled("staff"):
		return
	s = frappe.get_cached_doc("School Settings")
	today = getdate(nowdate())
	if s.duty_alert_sent_on and getdate(s.duty_alert_sent_on) == today:
		return
	if now_datetime().time() < get_time(s.duty_report_due_time or "17:00:00"):
		return
	missing = [
		m for m in on_duty_today(today)
		if not frappe.db.exists("Duty Report", {"staff_member": m, "report_date": today, "docstatus": 1})
	]
	frappe.db.set_single_value("School Settings", "duty_alert_sent_on", today)
	if not missing:
		return
	names = ", ".join(frappe.db.get_value("Staff Member", m, "full_name") for m in missing)
	notify(_("Please submit today's duty report"), _("Your Teacher on Duty report for today has not been submitted."),
		   staff=missing, sms_text="Reminder: please submit today's Teacher on Duty report.")
	notify(_("Duty report not submitted today: {0}").format(names), users=duty_report_recipients(), sms=False)


def duty_report_recipients() -> list[str]:
	user = frappe.db.get_single_value("School Settings", "duty_report_recipient")
	return [user] if user else head_teacher_users()


@frappe.whitelist()
def my_staff_record():
	return staff_for_user()
