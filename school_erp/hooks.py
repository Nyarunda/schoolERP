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

app_include_js = "/assets/school_erp/js/school_erp.js"

boot_session = "school_erp.licensing.boot_session"

# Jinja helpers available in print formats
jinja = {
	"methods": [
		"school_erp.api.statement.render_fee_statement",
		"school_erp.api.statement.get_statement_data",
		"school_erp.api.timetable.get_timetable_grid",
	]
}

# Every School DocType is checked against the license on save/submit
_licensed = "school_erp.licensing.enforce_on_doc"
doc_events = {
	dt: {"validate": _licensed, "before_submit": _licensed}
	for dt in (
		"School Fee Structure",
		"Fee Type",
		"Fee Billing Run",
		"Fee Payment",
		"Transport Route",
		"School Activity",
		"Timetable",
		"Subject",
		"Period",
		"School Message",
	)
}

doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
}

# Custom SMS sender (used when School Settings > SMS Provider = "Custom Hook").
# Another app can add:  school_sms_sender = "my_app.sms.send"  with signature send(numbers: list[str], message: str) -> dict
school_sms_sender = []

scheduler_events = {
	"daily": ["school_erp.licensing.daily_license_check"],
}

fixtures = []
