import frappe

from school_erp.logic.timetable import build_grid


def get_timetable_grid(timetable):
	"""Jinja helper for the Class Timetable print format."""
	doc = frappe.get_doc("Timetable", timetable) if isinstance(timetable, str) else timetable
	periods = frappe.get_all(
		"Period", fields=["name", "period_name", "sequence", "start_time", "end_time", "is_break"], order_by="sequence"
	)
	subjects = {
		s.name: s for s in frappe.get_all("Subject", fields=["name", "short_name", "color"])
	}
	teachers = {t.name: t.teacher_name for t in frappe.get_all("Teacher", fields=["name", "teacher_name"])}
	slots = []
	for s in doc.slots:
		sub = subjects.get(s.subject)
		slots.append(
			{
				"day": s.day,
				"period": s.period,
				"subject": s.subject,
				"label": (sub.short_name if sub and sub.short_name else s.subject) or "",
				"color": sub.color if sub else None,
				"teacher": teachers.get(s.teacher, ""),
				"room": s.room or "",
			}
		)
	for p in periods:
		p["time"] = f"{_hm(p.start_time)}-{_hm(p.end_time)}"
	return build_grid(slots, periods)


def _hm(t):
	"""timedelta / time / 'H:MM:SS' -> 'HH:MM'"""
	parts = str(t or "0:00").split(":")
	return f"{int(parts[0]):02d}:{parts[1][:2]}"


@frappe.whitelist()
def teacher_timetable(teacher, school_term):
	frappe.has_permission("Timetable", "read", throw=True)
	return frappe.db.sql(
		"""select ts.day, ts.period, ts.subject, ts.room, t.stream
		from `tabTimetable Slot` ts join `tabTimetable` t on t.name = ts.parent
		where ts.teacher = %s and t.school_term = %s order by ts.day, ts.period""",
		(teacher, school_term),
		as_dict=True,
	)
