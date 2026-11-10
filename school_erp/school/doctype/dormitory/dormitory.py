# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from school_erp.logic.boarding import occupancy


class Dormitory(Document):
	def validate(self):
		from school_erp.api.boarding import active_count

		o = occupancy(self.capacity, active_count(self.name) if not self.is_new() else 0)
		self.occupied, self.free_beds = o["occupied"], o["free"]
