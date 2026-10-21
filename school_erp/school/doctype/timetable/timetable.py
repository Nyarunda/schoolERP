# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from school_erp.logic.timetable import find_duplicate_slots, find_teacher_clashes


class Timetable(Document):
	def autoname(self):
		self.name = f"{self.stream} - {self.school_term}"

	def validate(self):
		if self.copy_from and not self.slots:
			src = frappe.get_doc("Timetable", self.copy_from)
			for s in src.slots:
				self.append("slots", {k: s.get(k) for k in ("day", "period", "subject", "teacher", "room")})
		self.copy_from = None

		slots = [s.as_dict() for s in self.slots]
		errors = find_duplicate_slots(slots)
		breaks = set(frappe.get_all("Period", filters={"is_break": 1}, pluck="name"))
		for s in self.slots:
			if s.period in breaks and s.subject:
				errors.append(_("Row {0}: {1} is a break").format(s.idx, s.period))
		errors += find_teacher_clashes(slots, self.other_slots())
		if errors:
			frappe.throw("<br>".join(errors), title=_("Timetable problems"))

	def other_slots(self):
		return frappe.db.sql(
			"""select ts.day, ts.period, ts.teacher, t.name as timetable, tc.teacher_name
			from `tabTimetable Slot` ts
			join `tabTimetable` t on t.name = ts.parent
			left join `tabTeacher` tc on tc.name = ts.teacher
			where t.school_term = %s and t.name != %s and ifnull(ts.teacher, '') != ''""",
			(self.school_term, self.name or ""),
			as_dict=True,
		)
