# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, add_months, get_first_day, get_last_day

from school_erp.api.report_utils import col, date_range
from school_erp import licensing


@licensing.licensed("Leave Application")
def execute(filters=None):
	f = frappe._dict(filters or {})
	from school_erp.api.staff import leave_balances

	year = int(f.year or getdate(nowdate()).year)
	staff_filters = {"status": ("!=", "Left")}
	if f.staff_type:
		staff_filters["staff_type"] = f.staff_type
	types = frappe.get_all("Leave Type", filters={"days_per_year": (">", 0)}, pluck="name", order_by="name")
	columns = [col("staff_member", "Staff", "Link", 110, "Staff Member"), col("full_name", "Name", "Data", 180),
			   col("staff_type", "Type", "Data", 110)]
	for t in types:
		columns += [col(f"{t}|taken", f"{t} taken", "Float", 110), col(f"{t}|balance", f"{t} left", "Float", 110)]
	data = []
	for s in frappe.get_all("Staff Member", filters=staff_filters, fields=["name", "full_name", "staff_type"], order_by="full_name"):
		row = {"staff_member": s.name, "full_name": s.full_name, "staff_type": s.staff_type}
		for b in leave_balances(s.name, year):
			if b["leave_type"] in types:
				row[f"{b['leave_type']}|taken"] = b["taken"]
				row[f"{b['leave_type']}|balance"] = b["balance"]
		data.append(row)
	return columns, data
