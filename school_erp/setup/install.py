import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ["School Admin", "Bursar", "Teacher"]


def before_install():
	make_roles()


def after_install():
	make_roles()
	make_custom_fields()
	make_customer_group()


def after_migrate():
	make_custom_fields()


def make_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def make_customer_group():
	if frappe.db.exists("Customer Group", "Students") or not frappe.db.exists("Customer Group", "All Customer Groups"):
		return
	frappe.get_doc(
		{"doctype": "Customer Group", "customer_group_name": "Students", "parent_customer_group": "All Customer Groups"}
	).insert(ignore_permissions=True)


def make_custom_fields():
	create_custom_fields(
		{
			"Customer": [
				dict(fieldname="student", label="Student", fieldtype="Link", options="Student",
					 insert_after="customer_name", read_only=1, in_standard_filter=1),
			],
			"Sales Invoice": [
				dict(fieldname="school_section", label="School", fieldtype="Section Break",
					 insert_after="customer_name", collapsible=1, depends_on="student"),
				dict(fieldname="student", label="Student", fieldtype="Link", options="Student",
					 insert_after="school_section", read_only=1, in_standard_filter=1, search_index=1),
				dict(fieldname="school_term", label="Term", fieldtype="Link", options="School Term",
					 insert_after="student", read_only=1, in_standard_filter=1, search_index=1),
				dict(fieldname="fee_billing_run", label="Fee Billing Run", fieldtype="Link",
					 options="Fee Billing Run", insert_after="school_term", read_only=1, no_copy=1),
			],
			"Sales Invoice Item": [
				dict(fieldname="fee_type", label="Fee Type", fieldtype="Link", options="Fee Type",
					 insert_after="item_name", in_list_view=0),
			],
			"Payment Entry": [
				dict(fieldname="student", label="Student", fieldtype="Link", options="Student",
					 insert_after="party_name", read_only=1, in_standard_filter=1),
				dict(fieldname="fee_payment", label="Fee Payment", fieldtype="Link", options="Fee Payment",
					 insert_after="student", read_only=1, no_copy=1),
			],
		},
		update=True,
	)
