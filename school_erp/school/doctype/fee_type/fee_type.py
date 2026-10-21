# Copyright (c) 2026, School ERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

ITEM_GROUP = "School Fees"


class FeeType(Document):
	def validate(self):
		self.ensure_item()

	def ensure_item(self):
		"""Each fee type is backed by a non-stock service Item so it can sit on a Sales Invoice."""
		ensure_item_group()
		settings = frappe.get_cached_doc("School Settings")
		income_account = self.income_account or settings.default_income_account
		item_code = self.item or self.fee_type_name

		if frappe.db.exists("Item", item_code):
			item = frappe.get_doc("Item", item_code)
		else:
			item = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": self.fee_type_name,
					"item_group": ITEM_GROUP,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
					"is_purchase_item": 0,
					"include_item_in_manufacturing": 0,
					"description": self.description or self.fee_type_name,
				}
			)

		if settings.company and income_account:
			row = next((d for d in item.get("item_defaults", []) if d.company == settings.company), None)
			if not row:
				row = item.append("item_defaults", {"company": settings.company})
			row.income_account = income_account
			if settings.cost_center:
				row.selling_cost_center = settings.cost_center

		item.flags.ignore_permissions = True
		item.save()
		self.item = item.name


def ensure_item_group():
	if not frappe.db.exists("Item Group", ITEM_GROUP):
		parent = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ("in", ["", None])}) or "All Item Groups"
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": parent, "is_group": 0}
		).insert(ignore_permissions=True)
