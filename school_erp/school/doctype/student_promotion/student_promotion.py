# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from school_erp.logic.promotion import apply_action, plan_student, summarize


class StudentPromotion(Document):
	def validate(self):
		if self.from_year == self.to_year:
			frappe.throw(_("Pick a different year to promote into"))
		if self.docstatus == 0:
			self.status = "Draft"
			self.refresh_plan()
		classes = ", ".join(c.school_class for c in self.classes) or _("Whole school")
		self.title = f"{self.from_year} → {self.to_year}: {classes}"[:140]

	def next_class_map(self):
		return dict(frappe.get_all("School Class", fields=["name", "next_class"], as_list=True))

	@frappe.whitelist()
	def get_students(self):
		"""Fill the list with every active student in the chosen classes and their default action."""
		if self.docstatus != 0:
			frappe.throw(_("Already promoted"))
		filters = {"status": "Active"}
		classes = [c.school_class for c in self.classes]
		if classes:
			filters["school_class"] = ("in", classes)
		nxt = self.next_class_map()
		from school_erp.api.payments import party_balance

		self.set("items", [])
		for s in frappe.get_all("Student", filters=filters, fields=["name", "student_name", "school_class", "stream"],
								order_by="school_class, stream, student_name"):
			plan = plan_student(s.school_class, s.stream, nxt.get(s.school_class))
			self.append("items", {
				"student": s.name, "student_name": s.student_name, "current_class": s.school_class, "current_stream": s.stream,
				"action": plan["action"], "new_class": plan["new_class"], "new_stream": plan["new_stream"],
				"balance": party_balance(s.name), "status": "Pending",
			})
		self.refresh_plan()
		return {"students": len(self.items)}

	def refresh_plan(self):
		"""Recompute destinations after the user changes an action, and the summary."""
		nxt = self.next_class_map()
		for i in self.items:
			dest = apply_action(i.action, i.current_class, i.current_stream, nxt.get(i.current_class))
			i.action, i.new_class, i.new_stream = dest["action"], dest["new_class"], dest["new_stream"]
			if i.action == "Graduate":
				i.new_stream = _("Graduates")
			elif i.action == "Left School":
				i.new_stream = _("Leaves school")
		s = summarize([{"action": i.action, "balance": flt(i.balance)} for i in self.items])
		self.total_students, self.to_promote, self.to_graduate, self.to_repeat = s["total"], s["promote"], s["graduate"], s["repeat"]
		self.with_balance, self.balance_total = s["with_balance"], s["balance"]

	def before_submit(self):
		if not self.items:
			frappe.throw(_("Click 'Get Students' first"))
		missing = sorted({i.new_class for i in self.items if i.action == "Promote" and not i.new_stream})
		if missing and not self.create_streams:
			frappe.throw(_("Some students have no stream to move into ({0}). Tick 'Create missing streams'.").format(", ".join(missing)))

	def on_submit(self):
		errors = 0
		for i in self.items:
			try:
				self.apply(i)
				frappe.db.set_value("Student Promotion Item", i.name, {"status": "Done", "note": None})
			except Exception as e:
				errors += 1
				frappe.db.set_value("Student Promotion Item", i.name, {"status": "Error", "note": str(e)[:140]})
		if self.make_to_year_current:
			doc = frappe.get_doc("School Year", self.to_year)
			doc.is_current = 1
			doc.save(ignore_permissions=True)
		self.db_set("status", "Completed with Errors" if errors else "Completed")

	def apply(self, item):
		student = frappe.get_doc("Student", item.student)
		if item.action == "Repeat":
			return
		if item.action in ("Graduate", "Left School"):
			student.status = "Graduated" if item.action == "Graduate" and self.graduate_status == "Graduated" else "Left"
			student.flags.ignore_permissions = True
			student.save()
			return
		stream = item.new_stream if frappe.db.exists("Stream", item.new_stream or "") else self.ensure_stream(item)
		student.stream = stream
		student.school_class = item.new_class
		student.flags.ignore_permissions = True
		student.save()

	def ensure_stream(self, item):
		from school_erp.logic.promotion import stream_suffix

		suffix = stream_suffix(item.current_stream, item.current_class) or "A"
		name = f"{item.new_class} {suffix}"
		if not frappe.db.exists("Stream", name):
			if not self.create_streams:
				frappe.throw(_("Stream {0} does not exist").format(name))
			frappe.get_doc({"doctype": "Stream", "school_class": item.new_class, "stream_name": suffix}).insert(ignore_permissions=True)
		return name

	def on_cancel(self):
		frappe.throw(_("A promotion cannot be cancelled. Move individual students back by editing them."))
