"""Driver morning check-in, vehicle checks and alerts to the transport manager."""

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, get_time, getdate, now_datetime, nowdate

from school_erp import licensing
from school_erp.api.notify import notify, staff_for_user
from school_erp.logic.operations import DEFAULT_CHECKLIST


def manager_users() -> list[str]:
	s = frappe.get_cached_doc("School Settings")
	if s.transport_manager_user:
		return [s.transport_manager_user]
	from school_erp.api.notify import users_for_role

	return users_for_role("Transport Manager") or ([s.head_teacher_user] if s.head_teacher_user else [])


@frappe.whitelist()
def driver_defaults():
	"""Pre-fill the form for the driver who is logged in."""
	staff = staff_for_user()
	out = {"driver": staff, "vehicle": None, "route": None, "checklist": DEFAULT_CHECKLIST}
	if staff:
		out["vehicle"] = frappe.db.get_value("Staff Member", staff, "default_vehicle") or frappe.db.get_value(
			"School Vehicle", {"default_driver": staff, "is_active": 1})
		out["route"] = frappe.db.get_value("Transport Route", {"driver": staff, "is_active": 1})
		if not out["vehicle"] and out["route"]:
			out["vehicle"] = frappe.db.get_value("Transport Route", out["route"], "vehicle")
	if out["vehicle"]:
		out["odometer_start"] = frappe.db.get_value("School Vehicle", out["vehicle"], "last_odometer")
	return out


def alert_missing_checkins():
	"""Runs every 15 minutes in the morning: once the deadline passes, report drivers who have not checked in."""
	if not licensing.is_enabled("transport_ops"):
		return
	s = frappe.get_cached_doc("School Settings")
	today = getdate(nowdate())
	if today.weekday() == 6:
		return
	if s.checkin_alert_sent_on and getdate(s.checkin_alert_sent_on) == today:
		return
	if now_datetime().time() < get_time(s.driver_checkin_deadline or "06:30:00"):
		return
	frappe.db.set_single_value("School Settings", "checkin_alert_sent_on", today)
	missing = missing_checkins(today)
	if not missing:
		return
	lines = [f"{m['driver_name']} ({m['route']})" for m in missing]
	notify(
		_("{0} driver(s) have not checked in").format(len(missing)),
		_("No morning check-in yet from: {0}").format(", ".join(lines)),
		users=manager_users(),
		sms_text="Not checked in yet: " + ", ".join(lines),
	)
	notify(_("Please complete your morning check-in"), staff=[m["driver"] for m in missing],
		   sms_text="Reminder: complete your morning vehicle check-in before leaving for pickup.")


def missing_checkins(day) -> list[dict]:
	routes = frappe.get_all("Transport Route", filters={"is_active": 1, "driver": ("is", "set")}, fields=["name", "driver"])
	out = []
	for r in routes:
		if frappe.db.get_value("Staff Member", r.driver, "status") == "On Leave":
			continue
		if not frappe.db.exists("Driver Daily Log", {"driver": r.driver, "log_date": day, "trip": "Morning Pickup", "docstatus": 1}):
			out.append({"driver": r.driver, "driver_name": frappe.db.get_value("Staff Member", r.driver, "full_name"), "route": r.name})
	return out


def alert_expiring_documents():
	"""Daily: insurance, inspection and driving licences expiring within 14 days."""
	if not licensing.is_enabled("transport_ops"):
		return
	today = getdate(nowdate())
	soon = add_days(today, 14)
	items = []
	for v in frappe.get_all("School Vehicle", filters={"is_active": 1},
							fields=["name", "insurance_expiry", "inspection_expiry", "speed_governor_expiry"]):
		for label, d in (("insurance", v.insurance_expiry), ("inspection", v.inspection_expiry), ("speed governor", v.speed_governor_expiry)):
			if d and getdate(d) <= soon:
				items.append(f"{v.name} {label} {'EXPIRED' if getdate(d) < today else 'expires'} {formatdate(d, 'd MMM')}")
	for d in frappe.get_all("Staff Member", filters={"staff_type": "Driver", "status": ("!=", "Left"),
													 "driving_license_expiry": ("<=", soon)}, fields=["full_name", "driving_license_expiry"]):
		items.append(f"{d.full_name} driving licence expires {formatdate(d.driving_license_expiry, 'd MMM')}")
	if items:
		notify(_("Transport documents expiring"), "\n".join(items), users=manager_users(),
			   sms=today.weekday() == 0, sms_text="Expiring: " + "; ".join(items[:5]))  # SMS weekly (Mondays), bell daily
