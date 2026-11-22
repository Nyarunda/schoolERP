app_name = "stemic_control"
app_title = "Stemic Schools Admin"
app_publisher = "Stemic"
app_description = "Separate multi-tenant SaaS control plane for Stemic Schools"
app_email = "support@stemicschools.com"
app_license = "mit"

# The admin site's login and web pages: Stemic's footer and icons. update_website_context runs after every app's
# website_context, so this holds even though ERPNext (installed after this app) sets its own favicon and splash image.
update_website_context = ["stemic_control.branding.website_context"]

add_to_apps_screen = [
    {
        "name": "stemic_control",
        "logo": "/assets/stemic_control/images/stemic.svg",
        "title": "Stemic Control",
        "route": "/desk/stemic-control",
        "has_permission": "stemic_control.permissions.has_app_permission",
    }
]

# Install only on admin.stemicschools.com, never on school tenant sites.
after_install = "stemic_control.setup.install"
after_migrate = "stemic_control.setup.after_migrate"

# Agents only see the schools and subscriptions they brought in
permission_query_conditions = {
    "SaaS Tenant": "stemic_control.permissions.tenant_query",
    "SaaS Subscription": "stemic_control.permissions.subscription_query",
    "SaaS Agent": "stemic_control.permissions.agent_query",
    "SaaS Invoice": "stemic_control.permissions.invoice_query",
    "SaaS Payment": "stemic_control.permissions.payment_query",
    "SaaS Commission": "stemic_control.permissions.commission_query",
}
has_permission = {
    "SaaS Tenant": "stemic_control.permissions.tenant_has_permission",
    "SaaS Subscription": "stemic_control.permissions.subscription_has_permission",
    "SaaS Agent": "stemic_control.permissions.agent_has_permission",
    "SaaS Invoice": "stemic_control.permissions.invoice_has_permission",
    "SaaS Payment": "stemic_control.permissions.payment_has_permission",
    "SaaS Commission": "stemic_control.permissions.commission_has_permission",
}

# Admin KPI page only; keep the school tenant app unaffected.
app_include_js = ["stemic_control.bundle.js"]
app_include_css = ["stemic_overview.bundle.css"]  # bundled: hashed file name, so browsers pick up changes

# Local provisioner safety net: picks up queued jobs and fails abandoned ones (only when switched on)
scheduler_events = {
    "cron": {"*/5 * * * *": ["stemic_control.provisioner.process_queue"], "*/15 * * * *": ["stemic_control.service.watch"]},
    # Billing: overdue invoices and Past Due subscriptions; renewal invoices ahead of the end date
    "daily": ["stemic_control.billing.daily", "stemic_control.billing.check_ledger", "stemic_control.service.check_certificates",
              "stemic_control.deletion.daily", "stemic_control.expenses.daily"],
    # Custom domains: keep the server's routes current; activate verified domains once they serve their school
    "hourly": ["stemic_control.domains.hourly", "stemic_control.backups.hourly", "stemic_control.service.auto_update"],
}

# Finance operators review tax records through controlled service actions.
doctype_js = {"SaaS eTIMS Invoice": "public/js/etims_invoice.js"}
