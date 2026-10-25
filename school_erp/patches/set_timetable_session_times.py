import frappe

from school_erp.school.doctype.timetable.timetable import set_session_times


def execute():
	"""Backfill Time and Session on lessons saved before those columns existed."""
	for name in frappe.get_all("Timetable", pluck="name"):
		doc = frappe.get_doc("Timetable", name)
		set_session_times(doc)
		for row in doc.slots:
			row.db_set({"time": row.time, "session": row.session}, update_modified=False)
