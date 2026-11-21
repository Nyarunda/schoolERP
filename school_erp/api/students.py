"""Graduate a learner, and move learners between classes (back after a promotion, up, or to another stream), one at
a time or several from the student list. Every change goes through the Student's own save rules, and a move leaves a
line on the learner's timeline saying from where, to where, why and who."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from school_erp.logic.promotion import move_kind

REASONS = ("Repeating the class", "Promoted by mistake", "Moved up a class", "Change of stream", "Other")
LEFT = ("Transferred", "Left", "Graduated")


def _can_edit(student=None):
	frappe.has_permission("Student", "write", doc=student, throw=True)


def _names(students):
	names = frappe.parse_json(students) if isinstance(students, str) and students.strip().startswith("[") else students
	names = [names] if isinstance(names, str) else list(names or [])
	if not names:
		frappe.throw(_("Choose at least one learner"))
	return names


def _term_invoice(student):
	from school_erp.school.doctype.school_term.school_term import get_current_term

	term = get_current_term()
	term = getattr(term, "name", term)  # the term's record, or its name
	if not term:
		return None
	return frappe.db.get_value("Sales Invoice", {"student": student, "school_term": term, "docstatus": 1, "is_return": 0},
							   "name")


# ----------------------------------------------------------------------------- move class
@frappe.whitelist(methods=["POST"])
def move_class(student, stream, reason, note=None):
	"""Put a learner in another stream (any class), with a reason. Returns where they went and any warning."""
	doc = frappe.get_doc("Student", student)
	_can_edit(doc)
	if reason not in REASONS:
		frappe.throw(_("Choose a reason: {0}").format(", ".join(REASONS)))
	if doc.status in LEFT:
		frappe.throw(_("{0} has left the school ({1}). Re-admit them first.").format(doc.student_name, doc.status))
	target = frappe.db.get_value("Stream", stream, ["name", "school_class", "is_active"], as_dict=True)
	if not target or not target.is_active:
		frappe.throw(_("{0} is not an active stream").format(stream))
	if target.name == doc.stream:
		frappe.throw(_("{0} is already in {1}").format(doc.student_name, stream))

	old_stream, old_class = doc.stream, doc.school_class
	levels = dict(frappe.get_all("School Class", filters={"name": ("in", [old_class, target.school_class])},
								 fields=["name", "level"], as_list=True))
	kind = move_kind(levels.get(old_class), levels.get(target.school_class))
	doc.stream, doc.school_class = target.name, target.school_class
	doc.save()

	who = frappe.utils.get_fullname(frappe.session.user)
	words = {"back": _("moved back"), "up": _("moved up"), "same class": _("moved to another stream")}[kind]
	text = _("{0}: from {1} to {2}. Reason: {3}.").format(words.capitalize(), old_stream or old_class or "-", target.name,
														  _(reason))
	if (note or "").strip():
		text += " " + note.strip()
	doc.add_comment("Info", text + " " + _("(by {0})").format(who))

	warning = None
	invoice = _term_invoice(doc.name)
	if invoice:
		warning = _("{0} already has invoice {1} for this term, raised for {2}. It was not changed: adjust it if the fees "
					"differ in {3}.").format(doc.student_name, invoice, old_class, target.school_class)
	return {"student": doc.name, "from": old_stream, "to": target.name, "kind": kind, "warning": warning}


@frappe.whitelist(methods=["POST"])
def bulk_move(students, stream, reason, note=None):
	"""Move several learners to one stream. Each is moved on its own; failures are reported, not fatal."""
	_can_edit()
	return _each(_names(students), lambda s: move_class(s, stream, reason, note))


# ----------------------------------------------------------------------------- graduate
@frappe.whitelist(methods=["POST"])
def graduate(student, leaving_date=None, note=None):
	doc = frappe.get_doc("Student", student)
	_can_edit(doc)
	if doc.status not in ("Active", "Suspended"):
		frappe.throw(_("Only an active learner can graduate; {0} is {1}").format(doc.student_name, doc.status))
	doc.status = "Graduated"
	doc.leaving_date = getdate(leaving_date or nowdate())
	doc.leaving_reason = (note or "").strip() or _("Graduated")
	doc.save()
	return {"student": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def bulk_graduate(students, leaving_date=None, note=None):
	_can_edit()
	return _each(_names(students), lambda s: graduate(s, leaving_date, note))


def _each(names, fn):
	done, failed, warnings = [], [], []
	for name in names:
		frappe.db.savepoint("student_bulk")
		try:
			out = fn(name)
			done.append(name)
			if out.get("warning"):
				warnings.append(out["warning"])
		except Exception as e:
			frappe.db.rollback(save_point="student_bulk")
			frappe.clear_messages()
			failed.append({"student": name, "error": frappe.utils.strip_html(str(e))})
	return {"done": len(done), "failed": failed, "warnings": warnings}


# ----------------------------------------------------------------------------- after a promotion
@frappe.whitelist()
def promoted_students(promotion):
	"""Learners a completed promotion moved up, who can still be moved back."""
	frappe.has_permission("Student Promotion", "read", doc=promotion, throw=True)
	return frappe.get_all("Student Promotion Item", filters={"parent": promotion, "parenttype": "Student Promotion",
															  "action": "Promote", "status": "Done"},
						  fields=["name", "student", "student_name", "current_stream", "new_stream"],
						  order_by="student_name")


@frappe.whitelist(methods=["POST"])
def move_back_from_promotion(promotion, student, reason="Repeating the class", note=None):
	"""Return a promoted learner to the stream they were promoted from, and mark that line on the promotion."""
	promo = frappe.get_doc("Student Promotion", promotion)
	if promo.docstatus != 1:
		frappe.throw(_("Only a completed promotion can be undone for a learner"))
	item = next((i for i in promo.items if i.student == student and i.action == "Promote" and i.status == "Done"), None)
	if not item:
		frappe.throw(_("{0} was not promoted by {1}, or was already moved back").format(student, promotion))
	if not frappe.db.exists("Stream", item.current_stream or ""):
		frappe.throw(_("The stream {0} no longer exists: use Move Class on the learner instead").format(item.current_stream))
	out = move_class(student, item.current_stream, reason,
					 (note or "").strip() or _("Moved back from year-end promotion {0}").format(promotion))
	frappe.db.set_value("Student Promotion Item", item.name,
						{"status": "Moved back", "note": _("Moved back to {0} on {1}").format(item.current_stream, nowdate())})
	return out
