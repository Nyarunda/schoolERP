"""Ready-made role profiles: a School Admin picks one job ("Head Teacher", "Bursar", "Secretary") on Staff Users
instead of ticking roles one by one among every ERPNext role.

Frappe makes a profiled user's roles exactly the profile's roles on each save. Some school roles are earned from
data instead (a staff record gives Staff + Teacher/Driver, a 'Reports To' gives Leave Approver, a subject gives Head
of Department), so keep_derived_roles puts those back. The ERPNext accounting roles are re-added by
finance.sync_user_roles, which runs after it.
"""

import frappe

# Profile -> school roles. Created on install/migrate; a school's own edits to a profile are kept (roles are only added).
PROFILES = {
	"School Admin": ["School Admin"],
	"Head Teacher": ["Head Teacher", "Teacher", "Leave Approver"],
	"Deputy Head Teacher": ["Head Teacher", "Teacher"],
	"Bursar": ["Bursar", "Staff"],
	"Head of Department": ["Head of Department", "Teacher", "Staff"],
	"Teacher": ["Teacher", "Staff"],
	"Secretary / Front Office": ["Staff"],
	"School Nurse": ["Staff"],
	"Librarian": ["Staff"],
	"Matron / House Parent": ["Staff"],
	"Canteen": ["Staff"],
	"Transport Manager": ["Transport Manager", "Staff"],
	"Driver": ["Driver", "Staff"],
	"Board / Auditor": ["School Viewer"],
}


def make_role_profiles():
	for name, roles in PROFILES.items():
		roles = [r for r in roles if frappe.db.exists("Role", r)]
		if not frappe.db.exists("Role Profile", name):
			doc = frappe.get_doc({"doctype": "Role Profile", "role_profile": name, "roles": [{"role": r} for r in roles]})
			doc.insert(ignore_permissions=True)
			continue
		doc = frappe.get_doc("Role Profile", name)
		missing = [r for r in roles if r not in {row.role for row in doc.roles}]
		if missing:
			for r in missing:
				doc.append("roles", {"role": r})
			doc.save(ignore_permissions=True)


def derived_roles(user: str) -> set[str]:
	"""School roles this login has earned from records, whatever profile it is on."""
	from school_erp.school.doctype.staff_member.staff_member import ROLE_FOR_TYPE

	roles = set()
	for sm in frappe.get_all("Staff Member", filters={"user": user, "status": ("!=", "Left")}, fields=["staff_type"]):
		roles.add("Staff")
		if ROLE_FOR_TYPE.get(sm.staff_type):
			roles.add(ROLE_FOR_TYPE[sm.staff_type])
	boss_of = frappe.db.sql(
		"""select 1 from `tabStaff Member` sm join `tabStaff Member` boss on boss.name = sm.reports_to
		where boss.user = %s and sm.status != 'Left' limit 1""", user)
	if boss_of or frappe.db.get_single_value("School Settings", "head_teacher_user") == user:
		roles.add("Leave Approver")
	if frappe.db.exists("Subject", {"head_of_department": user}):
		roles.add("Head of Department")
	return {r for r in roles if frappe.db.exists("Role", r)}


def keep_derived_roles(doc, method=None):
	"""User validate hook (before finance.sync_user_roles): a role profile must not take away earned roles."""
	if doc.name in ("Administrator", "Guest") or doc.is_new() or not doc.get("role_profiles"):
		return
	if not frappe.db.exists("DocType", "Staff Member"):
		return
	have = {r.role for r in doc.roles}
	for role in sorted(derived_roles(doc.name) - have):
		doc.append("roles", {"role": role})
