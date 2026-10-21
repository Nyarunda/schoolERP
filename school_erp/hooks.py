app_name = "school_erp"
app_title = "School ERP"
app_publisher = "School ERP"
app_description = "School management on ERPNext: students, term billing, statements, timetable, transport, lunch, activities and parent messaging"
app_email = "swartdata@gmail.com"
app_license = "mit"
required_apps = ["erpnext"]

add_to_apps_screen = [
	{
		"name": "school_erp",
		"logo": "/assets/school_erp/images/school.svg",
		"title": "School",
		"route": "/app/school",
	}
]

# Roles must exist before the DocTypes that reference them are synced
before_install = "school_erp.setup.install.before_install"
after_install = "school_erp.setup.install.after_install"
after_migrate = "school_erp.setup.install.after_migrate"
before_tests = "school_erp.tests.utils.before_tests"

app_include_js = ["/assets/school_erp/js/school_erp.js", "/assets/school_erp/js/school_dashboard.js"]
app_include_css = ["/assets/school_erp/css/school_dashboard.css"]

boot_session = "school_erp.licensing.boot_session"

# Jinja helpers available in print formats
jinja = {
	"methods": [
		"school_erp.api.statement.render_fee_statement",
		"school_erp.api.statement.get_statement_data",
		"school_erp.api.timetable.get_timetable_grid",
	]
}

# Every licensed School DocType is checked against the license on save/submit
from school_erp.logic.license import DOCTYPE_MODULE as _DOCTYPE_MODULE  # noqa: E402

_licensed = "school_erp.licensing.enforce_on_doc"
doc_events = {dt: {"validate": _licensed, "before_submit": _licensed} for dt in _DOCTYPE_MODULE}

# Staff see only their own leave, duty reports and driver logs (plus what they must approve)
permission_query_conditions = {
	"Leave Application": "school_erp.permissions.leave_query",
	"Duty Report": "school_erp.permissions.duty_report_query",
	"Driver Daily Log": "school_erp.permissions.driver_log_query",
	"School Expense": "school_erp.permissions.expense_query",
}
has_permission = {
	"Leave Application": "school_erp.permissions.leave_has_permission",
	"Duty Report": "school_erp.permissions.duty_report_has_permission",
	"Driver Daily Log": "school_erp.permissions.driver_log_has_permission",
	"School Expense": "school_erp.permissions.expense_has_permission",
}

doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
}

# Custom SMS sender (used when School Settings > SMS Provider = "Custom Hook").
# Another app can add:  school_sms_sender = "my_app.sms.send"  with signature send(numbers: list[str], message: str) -> dict
school_sms_sender = []

scheduler_events = {
	"daily": [
		"school_erp.licensing.daily_license_check",
		"school_erp.api.staff.update_staff_leave_status",
		"school_erp.api.transport_ops.alert_expiring_documents",
		"school_erp.school.doctype.school_notice.school_notice.publish_scheduled",
	],
	"hourly": ["school_erp.api.paybill.retry_pending"],
	"cron": {
		"*/15 4-10 * * 1-6": ["school_erp.api.transport_ops.alert_missing_checkins"],
		"*/30 15-20 * * 1-5": ["school_erp.api.staff.alert_missing_duty_reports"],
	},
}

fixtures = []
