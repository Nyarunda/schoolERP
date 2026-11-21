# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, nowdate

from school_erp.api import transport_ops
from school_erp.api.notify import notify, staff_for_user
from school_erp.logic.operations import DEFAULT_CHECKLIST, vehicle_problems


class DriverDailyLog(Document):
	def before_insert(self):
		self.check_in_time = now_datetime()

	def validate(self):
		if not self.driver:
			self.driver = staff_for_user()
		if not self.driver:
			frappe.throw(_("Your login is not linked to a driver (Staff Member)."))
		manager = set(frappe.get_roles()) & {"System Manager", "School Admin", "Head Teacher", "Transport Manager"}
		if not manager and self.driver != staff_for_user():
			frappe.throw(_("You can only check in for yourself"), frappe.PermissionError)
		if not self.checklist:
			for item in DEFAULT_CHECKLIST:
				self.append("checklist", {"item": item, "ok": 0})
		dup = frappe.db.get_value("Driver Daily Log", {"driver": self.driver, "log_date": self.log_date, "trip": self.trip,
														"docstatus": ("<", 2), "name": ("!=", self.name)})
		if dup and self.trip != "Other Trip":
			frappe.throw(_("{0} check-in for this day already exists: {1}").format(self.trip, dup))
		last = flt(frappe.db.get_value("School Vehicle", self.vehicle, "last_odometer"))
		if flt(self.odometer_start) and last and flt(self.odometer_start) < last:
			frappe.msgprint(_("Odometer {0} is lower than the last recorded {1}").format(self.odometer_start, last), indicator="orange")
		self.has_issues = int(bool(self.problems() or self.issues))
		self.set_distance()

	def problems(self):
		v = frappe.db.get_value("School Vehicle", self.vehicle, ["insurance_expiry", "inspection_expiry"], as_dict=True) or {}
		lic = frappe.db.get_value("Staff Member", self.driver, "driving_license_expiry")
		return vehicle_problems(
			[{"item": c.item, "ok": c.ok, "remarks": c.remarks} for c in self.checklist],
			bool(self.fit_to_drive), getdate(self.log_date or nowdate()),
			getdate(v.get("insurance_expiry")) if v.get("insurance_expiry") else None,
			getdate(v.get("inspection_expiry")) if v.get("inspection_expiry") else None,
			getdate(lic) if lic else None,
		)

	def set_distance(self):
		if flt(self.odometer_end) and flt(self.odometer_start):
			if flt(self.odometer_end) < flt(self.odometer_start):
				frappe.throw(_("End odometer is lower than the start odometer"))
			self.distance_km = flt(self.odometer_end) - flt(self.odometer_start)

	def before_submit(self):
		if not self.fit_to_drive:
			frappe.throw(_("Tick 'I am fit to drive today' to check in. If you are not fit to drive, call the transport manager instead."))

	def on_submit(self):
		self.update_vehicle_odometer()
		transport_ops.raise_fuel_expense(self)
		problems = self.problems() + ([f"Driver notes: {self.issues}"] if self.issues else [])
		if problems:
			notify(
				_("Vehicle check issues: {0} ({1})").format(self.vehicle, self.driver_name),
				"\n".join(problems), users=transport_ops.manager_users(), doc=self,
				sms_text=f"{self.vehicle} / {self.driver_name}: " + "; ".join(problems)[:300],
			)

	def on_update_after_submit(self):
		self.set_distance()
		self.db_set("distance_km", self.distance_km, update_modified=False)
		self.update_vehicle_odometer()
		before = self.get_doc_before_save()
		if self.fuel_expense:
			transport_ops.fuel_cost_changed(self, before.fuel_cost if before else self.fuel_cost)
		else:
			transport_ops.raise_fuel_expense(self)

	def on_cancel(self):
		transport_ops.drop_fuel_expense(self)

	def update_vehicle_odometer(self):
		reading = max(flt(self.odometer_start), flt(self.odometer_end))
		if reading > flt(frappe.db.get_value("School Vehicle", self.vehicle, "last_odometer")):
			frappe.db.set_value("School Vehicle", self.vehicle, "last_odometer", reading, update_modified=False)
