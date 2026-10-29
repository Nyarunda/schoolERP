import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ["School Admin", "Bursar", "Teacher", "Head Teacher", "Staff", "Driver", "Transport Manager", "Leave Approver",
	"School Viewer"]


def before_install():
	make_roles()


def after_install():
	make_roles()
	make_custom_fields()
	make_customer_group()
	fill_new_settings_defaults()
	make_workflows()
	setup_finance()
	setup_viewer()


def after_migrate():
	make_roles()
	make_custom_fields()
	fill_new_settings_defaults()
	make_workflows()
	setup_finance()
	setup_viewer()


def setup_viewer():
	from school_erp.setup.viewer import setup

	setup()


def setup_finance():
	from school_erp.setup.finance import setup_finance as _setup

	_setup()


def make_workflows():
	from school_erp.setup.workflows import make_workflows as _make

	_make()


def fill_new_settings_defaults():
	"""When an upgrade adds School Settings fields, store their defaults once.
	Only fields with no stored value at all are touched, so a school's own choices are never overwritten."""
	meta = frappe.get_meta("School Settings")
	stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype = 'School Settings'"))
	for df in meta.fields:
		if df.default and df.fieldname not in stored and df.fieldtype not in ("Link", "Dynamic Link"):
			frappe.db.set_single_value("School Settings", df.fieldname, df.default, update_modified=False)


PORTAL_ROLES = ["Parent"]  # website-only: no desk access


def make_roles():
	for role in ROLES + PORTAL_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": int(role not in PORTAL_ROLES)}).insert(ignore_permissions=True)


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
