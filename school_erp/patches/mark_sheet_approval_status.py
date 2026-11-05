"""Mark sheets submitted before marks approval existed count as approved; drafts stay drafts."""

import frappe


def execute():
	frappe.db.sql("""update `tabExam Mark Sheet` set approval_status = case docstatus
		when 1 then 'Approved' when 2 then 'Cancelled' else 'Draft' end
		where ifnull(approval_status, '') in ('', 'Draft')""")
	frappe.db.sql("""update `tabExam Mark Sheet` set approved_by = modified_by, approved_on = modified
		where docstatus = 1 and ifnull(approved_by, '') = ''""")
