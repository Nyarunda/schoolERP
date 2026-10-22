# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from school_erp.api import staff as staff_api
from school_erp.api.notify import notify, staff_for_user
from school_erp.logic.operations import leave_problems


class LeaveApplication(Document):
	def validate(self):
		if not self.staff_member:
			self.staff_member = staff_for_user()
		# applicants edit their own request; the approver only changes the status through the workflow
		if self.is_new() or (self.status == "Pending Approval" and frappe.session.user != self.approver):
			self.check_applicant()
		self.total_days = staff_api.count_days(self.leave_type, self.from_date, self.to_date)
		year = getdate(self.from_date).year
		taken = staff_api.days_taken(self.staff_member, self.leave_type, year, exclude=self.name)
		entitled = frappe.db.get_value("Leave Type", self.leave_type, "days_per_year") or 0
		self.balance_before = (entitled - taken) if entitled else 0
		if self.docstatus == 0:
			self.approver = staff_api.approver_for(self.staff_member)
		if not self.status:
			self.status = "Pending Approval"
		if self.status == "Rejected" and not (self.decision_comment or "").strip():
			frappe.throw(_("Give a reason for rejecting (Comment)"), title=_("Reason required"))

		lt = frappe.get_cached_doc("Leave Type", self.leave_type).as_dict()
		staff = frappe.db.get_value("Staff Member", self.staff_member, ["name", "gender", "staff_type", "status"], as_dict=True)
		if staff.status == "Left":
			frappe.throw(_("{0} has left the school").format(self.staff_name))
		problems = leave_problems(
			{"from_date": getdate(self.from_date), "to_date": getdate(self.to_date), "total_days": self.total_days,
			 "reliever": self.reliever, "attachment": self.attachment},
			lt, staff, taken, self.overlapping(self.staff_member), reliever_busy=bool(self.reliever and self.overlapping(self.reliever)),
		)
		if problems:
			frappe.throw("<br>".join(_(p) for p in problems), title=_("Cannot apply for this leave"))

	def check_applicant(self):
		"""Ordinary staff can only apply for themselves; managers can apply on anyone's behalf."""
		if staff_api.is_manager():
			return
		mine = staff_for_user()
		if not mine:
			frappe.throw(_("Your login is not linked to a Staff Member. Ask the school office to link it."))
		if self.staff_member != mine:
			frappe.throw(_("You can only apply for your own leave"), frappe.PermissionError)

	def overlapping(self, staff_member):
		return frappe.get_all(
			"Leave Application",
			filters={
				"staff_member": staff_member,
				"docstatus": ("<", 2),
				"status": ("in", ["Pending Approval", "Approved"]),
				"name": ("!=", self.name or ""),
				"from_date": ("<=", self.to_date),
				"to_date": (">=", self.from_date),
			},
			pluck="name",
		)

	def after_insert(self):
		if self.approver:
			notify(
				_("Leave request: {0}, {1} ({2} day(s))").format(self.staff_name, self.leave_type, self.total_days),
				_("{0} has applied for {1} from {2} to {3}. Reason: {4}").format(
					self.staff_name, self.leave_type, self.from_date, self.to_date, self.reason),
				users=[self.approver], doc=self,
				sms_text=f"Leave request from {self.staff_name}: {self.leave_type}, {self.total_days:g} day(s) from {self.from_date}. Please approve or reject in the system.",
			)

	def before_submit(self):
		# reached through the Workflow's Approve / Reject actions
		if self.status not in ("Approved", "Rejected"):
			frappe.throw(_("Use the Approve or Reject action"))
		self.approved_by = frappe.session.user
		self.decision_date = frappe.utils.now_datetime()

	def on_submit(self):
		staff_api.notify_leave_decision(self)
		staff_api.update_staff_leave_status()

	def on_cancel(self):
		before = self.get_doc_before_save()
		was_approved = bool(before and before.status == "Approved")
		self.db_set("status", "Cancelled")
		staff_api.update_staff_leave_status()
		if was_approved and self.reliever:
			notify(_("Relieving cancelled: {0}").format(self.staff_name),
				   _("{0}'s {1} has been cancelled; you no longer need to relieve them.").format(self.staff_name, self.leave_type),
				   staff=[self.reliever], doc=self,
				   sms_text=f"{self.staff_name}'s leave has been cancelled. You no longer need to relieve them.")
