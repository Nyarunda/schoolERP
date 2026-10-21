"""Small helpers shared by the School reports."""

from frappe import _
from frappe.utils import get_first_day, getdate, nowdate


def col(fieldname, label, fieldtype="Data", width=120, options=None):
	c = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
	if options:
		c["options"] = options
	return c


def date_range(filters):
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or get_first_day(to_date))
	return from_date, to_date
